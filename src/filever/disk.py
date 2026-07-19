from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .discover import PathVersions, discover
from .errors import AmbiguousVersion, NoVersionFound, UnresolvedPlaceholder
from .rewrite import DriverArg, _global_span, _resolve_driver, _splice
from .tokens import VersionToken


@dataclass(frozen=True)
class DiskVersion:
    value: int
    path: str
    is_symlink: bool


def _to_pv(pv_or_path: PathVersions | str) -> PathVersions:
    if isinstance(pv_or_path, PathVersions):
        return pv_or_path
    return discover(pv_or_path)


def _check_no_placeholders(pv: PathVersions) -> None:
    if pv.placeholders:
        raise UnresolvedPlaceholder(
            f"disk operations require a resolved path (no #### or %0Nd tokens): {pv.path!r}"
        )


def _parent_of_part(pv: PathVersions, token: VersionToken) -> str:
    _text, offset = pv.parts[token.part_index]
    parent = pv.path[:offset]
    while parent and parent[-1] in ("/", "\\"):
        parent = parent[:-1]
    if not parent:
        if pv.path.startswith("/"):
            return "/"
        if pv.path.startswith("\\"):
            return "\\"
        return "."
    return parent


def _scan_candidate_entries(pv: PathVersions, driver: VersionToken) -> dict[int, str]:
    part_text, _ = pv.parts[driver.part_index]
    v_start, v_end = driver.span
    prefix = re.escape(part_text[:v_start] + driver.case)
    suffix = re.escape(part_text[v_end:])
    entry_re = re.compile(f"^{prefix}(\\d+){suffix}$", re.IGNORECASE)
    parent = _parent_of_part(pv, driver)
    try:
        entries = os.listdir(parent)
    except OSError:
        return {}
    found: dict[int, str] = {}
    for entry in sorted(entries):
        m = entry_re.match(entry)
        if not m:
            continue
        digits = m.group(1)
        value = int(digits)
        if digits != f"{value:0{driver.pad}d}":
            continue
        if value not in found:
            found[value] = entry
    return found


def _driver_and_group(
    pv: PathVersions, driver: DriverArg
) -> tuple[VersionToken, list[VersionToken]]:
    if not pv.versions:
        raise NoVersionFound(f"no version tokens on path: {pv.path!r}")
    if driver is not None:
        _resolve_driver(pv, driver)
    if pv.agrees():
        return pv.versions[0], list(pv.versions)
    if driver is None:
        raise AmbiguousVersion(
            f"path has mismatched version tokens and no driver= supplied: {pv.path!r}"
        )
    driver_token = _resolve_driver(pv, driver)
    group = [v for v in pv.versions if v.value == driver_token.value and v.pad == driver_token.pad]
    if not group:
        group = [driver_token]
    return driver_token, group


def find_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[DiskVersion]:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, group = _driver_and_group(pv, driver)
    candidates = _scan_candidate_entries(pv, driver_token)
    if not candidates:
        return []
    driver_part_text, driver_part_offset = pv.parts[driver_token.part_index]
    driver_part_end = driver_part_offset + len(driver_part_text)
    result: list[DiskVersion] = []
    seen_reals: set[str] = set()
    for value in sorted(candidates):
        entry_name = candidates[value]
        driver_edit = (driver_part_offset, driver_part_end, entry_name)
        other_edits = [
            (*_global_span(pv, t), t.format(value)) for t in group if t is not driver_token
        ]
        candidate_path = _splice(pv.path, [driver_edit, *other_edits])
        if not os.path.exists(candidate_path):
            continue
        is_link = os.path.islink(candidate_path)
        if is_link and not include_symlinks:
            continue
        real = os.path.realpath(candidate_path)
        if real in seen_reals:
            continue
        seen_reals.add(real)
        result.append(DiskVersion(value=value, path=candidate_path, is_symlink=is_link))
    return result


def list_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[int]:
    return [
        dv.value
        for dv in find_on_disk(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    ]


def latest_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> int | None:
    versions = list_on_disk(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    return max(versions) if versions else None


def earliest_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> int | None:
    versions = list_on_disk(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    return min(versions) if versions else None


def next_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    exists: bool = True,
    include_symlinks: bool = False,
) -> int | None:
    pv = _to_pv(pv_or_path)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    if not exists:
        return current + 1
    _check_no_placeholders(pv)
    higher = [
        v for v in list_on_disk(pv, driver=driver, include_symlinks=include_symlinks) if v > current
    ]
    return min(higher) if higher else None


def previous_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    exists: bool = True,
    include_symlinks: bool = False,
) -> int | None:
    pv = _to_pv(pv_or_path)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    if not exists:
        return current - 1 if current > 0 else None
    _check_no_placeholders(pv)
    lower = [
        v for v in list_on_disk(pv, driver=driver, include_symlinks=include_symlinks) if v < current
    ]
    return max(lower) if lower else None
