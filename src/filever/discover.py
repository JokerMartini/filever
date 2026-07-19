from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .tokens import PlaceholderNotation, PlaceholderToken, VersionToken

_VERSION_RE = re.compile(r"(?<![A-Za-z0-9])([vV])(\d+)(?![A-Za-z0-9])")
_PRINTF_RE = re.compile(r"%0(\d+)d")
_HASH_RE = re.compile(r"#+")


def _split_parts(path: str) -> list[tuple[str, int]]:
    parts: list[tuple[str, int]] = []
    start = 0
    for i, ch in enumerate(path):
        if ch in ("/", "\\"):
            if i > start:
                parts.append((path[start:i], start))
            start = i + 1
    if start < len(path):
        parts.append((path[start:], start))
    return parts


def _find_versions_in_part(part: str, part_index: int) -> list[VersionToken]:
    matches: list[VersionToken] = []
    for m in _VERSION_RE.finditer(part):
        prefix, digits = m.group(1), m.group(2)
        matches.append(
            VersionToken(
                raw=m.group(0),
                value=int(digits),
                pad=len(digits),
                case=prefix,
                part_index=part_index,
                span=(m.start(), m.end()),
            )
        )
    return matches


def _find_placeholders_in_part(part: str, part_index: int) -> list[PlaceholderToken]:
    tokens: list[PlaceholderToken] = []
    for m in _PRINTF_RE.finditer(part):
        tokens.append(
            PlaceholderToken(
                raw=m.group(0),
                notation=PlaceholderNotation.PRINTF,
                width=int(m.group(1)),
                part_index=part_index,
                span=(m.start(), m.end()),
            )
        )
    for m in _HASH_RE.finditer(part):
        tokens.append(
            PlaceholderToken(
                raw=m.group(0),
                notation=PlaceholderNotation.HASH,
                width=len(m.group(0)),
                part_index=part_index,
                span=(m.start(), m.end()),
            )
        )
    tokens.sort(key=lambda t: t.span[0])
    return tokens


@dataclass(frozen=True)
class PathVersions:
    path: str
    parts: tuple[tuple[str, int], ...]
    versions: tuple[VersionToken, ...]
    placeholders: tuple[PlaceholderToken, ...]
    _all_version_candidates: tuple[VersionToken, ...] = field(default=(), repr=False)

    @property
    def filename_index(self) -> int:
        return len(self.parts) - 1

    @property
    def filename_version(self) -> VersionToken | None:
        for v in self.versions:
            if v.part_index == self.filename_index:
                return v
        return None

    @property
    def folder_versions(self) -> tuple[VersionToken, ...]:
        return tuple(v for v in self.versions if v.part_index != self.filename_index)

    def agrees(self) -> bool:
        if len(self.versions) < 2:
            return True
        first = self.versions[0]
        return all(v.value == first.value and v.pad == first.pad for v in self.versions[1:])

    def version_group_value(self) -> int | None:
        if not self.versions:
            return None
        if not self.agrees():
            return None
        return self.versions[0].value

    def by_part(self) -> dict[int, list[VersionToken]]:
        result: dict[int, list[VersionToken]] = {}
        for v in self.versions:
            result.setdefault(v.part_index, []).append(v)
        return result


def discover(path: str | os.PathLike, *, tiebreaker: str = "rightmost") -> PathVersions:
    if tiebreaker not in ("rightmost", "leftmost"):
        raise ValueError(f"tiebreaker must be 'rightmost' or 'leftmost', got {tiebreaker!r}")
    path_str = os.fspath(path)
    parts = _split_parts(path_str)

    versions: list[VersionToken] = []
    all_candidates: list[VersionToken] = []
    placeholders: list[PlaceholderToken] = []

    for idx, (part_text, _offset) in enumerate(parts):
        part_versions = _find_versions_in_part(part_text, idx)
        all_candidates.extend(part_versions)
        if part_versions:
            chosen = part_versions[-1] if tiebreaker == "rightmost" else part_versions[0]
            versions.append(chosen)
        placeholders.extend(_find_placeholders_in_part(part_text, idx))

    return PathVersions(
        path=path_str,
        parts=tuple(parts),
        versions=tuple(versions),
        placeholders=tuple(placeholders),
        _all_version_candidates=tuple(all_candidates),
    )
