"""A small, safe parser for the subset of Lua that WoW writes into SavedVariables files.

Never executes anything. Understands:
  Name = value            (top-level assignments, repeated)
  { ... }                 tables with ["key"] = v, [123] = v, or bare positional entries; trailing commas
  "strings"               with \\", \\\\, \\n, \\r, \\t, \\a, \\b, \\f, \\v, \\ddd and backslash-newline escapes
  numbers                 integers, floats, exponents, hex; plus the non-Lua spellings inf / -inf / nan / -nan(ind)
  true / false / nil      (nil as a positional entry advances the index, as Lua would)
  -- comments             (Blizzard never writes them, hand-edited files might)

Tables come back as dicts keyed by int or str. Use to_python() to turn 1..n dicts into lists.
"""
from __future__ import annotations

import math
import re
import sys
from typing import Any

MAX_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 500


class LuaParseError(ValueError):
    def __init__(self, message: str, pos: int, line: int):
        super().__init__(f"{message} (line {line}, offset {pos})")
        self.pos = pos
        self.line = line


class TornFile(LuaParseError):
    """The file ended in the middle of a value: WoW was probably still writing it."""


_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)
  | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<special>-?(?:inf|nan(?:\(ind\))?|1\.\#INF|1\.\#IND|1\.\#QNAN)(?![A-Za-z0-9_]))
  | (?P<number>-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[{}\[\]=,;])
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPES = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
    "\\": "\\", '"': '"', "'": "'", "\n": "\n",
}
_ESC_RE = re.compile(r"\\(\d{1,3}|x[0-9a-fA-F]{2}|z\s*|.)", re.DOTALL)


def _unescape(body: str) -> str:
    def repl(m: re.Match[str]) -> str:
        e = m.group(1)
        if e.isdigit():
            return chr(int(e))
        if e.startswith("x") and len(e) == 3:
            return chr(int(e[1:], 16))
        if e.startswith("z"):
            return ""
        return _ESCAPES.get(e, e)
    return _ESC_RE.sub(repl, body)


def _special(text: str) -> float:
    neg = text.startswith("-")
    core = text.lstrip("-").lower()
    if core.startswith("inf") or "inf" in core:
        return -math.inf if neg else math.inf
    return math.nan


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    # -- tokens -------------------------------------------------------------
    def _line(self, pos: int | None = None) -> int:
        return self.text.count("\n", 0, self.pos if pos is None else pos) + 1

    def next_token(self) -> tuple[str, str] | None:
        while self.pos < self.length:
            m = _TOKEN.match(self.text, self.pos)
            if not m:
                raise LuaParseError(f"unexpected character {self.text[self.pos]!r}", self.pos, self._line())
            self.pos = m.end()
            kind = m.lastgroup
            if kind in ("ws", "comment"):
                continue
            return kind, m.group(kind)  # type: ignore[arg-type]
        return None

    def peek(self) -> tuple[str, str] | None:
        saved = self.pos
        tok = self.next_token()
        self.pos = saved
        return tok

    def expect(self, kind: str, value: str | None = None) -> str:
        tok = self.next_token()
        if tok is None:
            raise TornFile(f"unexpected end of file, expected {value or kind}", self.pos, self._line())
        if tok[0] != kind or (value is not None and tok[1] != value):
            raise LuaParseError(f"expected {value or kind}, got {tok[1]!r}", self.pos, self._line())
        return tok[1]

    # -- grammar ------------------------------------------------------------
    def parse_chunk(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while True:
            tok = self.next_token()
            if tok is None:
                return out
            if tok[0] != "name":
                raise LuaParseError(f"expected a global name, got {tok[1]!r}", self.pos, self._line())
            name = tok[1]
            self.expect("punct", "=")
            out[name] = self.parse_value(0)

    def parse_value(self, depth: int) -> Any:
        tok = self.next_token()
        if tok is None:
            raise TornFile("unexpected end of file, expected a value", self.pos, self._line())
        kind, text = tok
        if kind == "punct" and text == "{":
            if depth >= MAX_DEPTH:
                raise LuaParseError("table nesting too deep", self.pos, self._line())
            return self.parse_table(depth + 1)
        if kind == "string":
            return _unescape(text[1:-1])
        if kind == "number":
            if text.lower().startswith(("0x", "-0x")):
                return int(text, 16)
            if re.fullmatch(r"-?\d+", text):
                return int(text)
            return float(text)
        if kind == "special":
            return _special(text)
        if kind == "name":
            if text == "true":
                return True
            if text == "false":
                return False
            if text == "nil":
                return None
            raise LuaParseError(f"unexpected identifier {text!r}", self.pos, self._line())
        raise LuaParseError(f"unexpected token {text!r}", self.pos, self._line())

    def parse_table(self, depth: int) -> dict[Any, Any]:
        table: dict[Any, Any] = {}
        index = 1
        while True:
            tok = self.peek()
            if tok is None:
                raise TornFile("unexpected end of file inside a table", self.pos, self._line())
            kind, text = tok
            if kind == "punct" and text == "}":
                self.next_token()
                return table
            if kind == "punct" and text == "[":
                self.next_token()
                key = self.parse_value(depth)
                if isinstance(key, float) and key.is_integer():
                    key = int(key)
                self.expect("punct", "]")
                self.expect("punct", "=")
                value = self.parse_value(depth)
                if value is not None:
                    table[key] = value
            elif kind == "name" and text not in ("true", "false", "nil"):
                # bare identifier key (hand-written files): key = value
                self.next_token()
                self.expect("punct", "=")
                value = self.parse_value(depth)
                if value is not None:
                    table[text] = value
            else:
                value = self.parse_value(depth)
                if value is not None:
                    table[index] = value
                index += 1
            sep = self.peek()
            if sep is None:
                raise TornFile("unexpected end of file inside a table", self.pos, self._line())
            if sep[0] == "punct" and sep[1] in (",", ";"):
                self.next_token()


def parse(text: str | bytes) -> dict[str, Any]:
    """Parse a SavedVariables file into {global_name: value}."""
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            raise LuaParseError("file too large", 0, 1)
        text = text.decode("utf-8", errors="surrogateescape")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    old_limit = sys.getrecursionlimit()
    if old_limit < MAX_DEPTH * 4:
        sys.setrecursionlimit(MAX_DEPTH * 4)
    try:
        return _Parser(text).parse_chunk()
    finally:
        sys.setrecursionlimit(old_limit)


def to_python(value: Any) -> Any:
    """Convert parsed tables: dicts keyed exactly 1..n become lists; everything else stays a dict (str keys)."""
    if isinstance(value, dict):
        if not value:
            return []  # Lua cannot tell an empty array from an empty map; empty list is the safer JSON default
        keys = list(value.keys())
        if all(isinstance(k, int) for k in keys):
            ordered = sorted(keys)
            if ordered == list(range(1, len(ordered) + 1)):
                return [to_python(value[k]) for k in ordered]
        return {str(k): to_python(v) for k, v in value.items()}
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return value
