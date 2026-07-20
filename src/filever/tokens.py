from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TokenClass(Enum):
    VERSION = "version"
    PLACEHOLDER = "placeholder"


class PlaceholderNotation(Enum):
    PRINTF = "printf"
    HASH = "hash"


@dataclass(frozen=True)
class VersionToken:
    raw: str
    value: int
    pad: int
    case: str
    part_index: int
    span: tuple[int, int]

    token_class = TokenClass.VERSION

    def format(self, value: int) -> str:
        return f"{self.case}{value:0{self.pad}d}"

    @property
    def formatted(self) -> str:
        return self.format(self.value)


@dataclass(frozen=True)
class VersionedFile:
    path: Path
    version: VersionToken


@dataclass(frozen=True)
class PlaceholderToken:
    raw: str
    notation: PlaceholderNotation
    width: int
    part_index: int
    span: tuple[int, int]

    token_class = TokenClass.PLACEHOLDER
