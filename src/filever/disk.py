from __future__ import annotations

import os
import re

from .discover import PathVersions, discover
from .errors import AmbiguousVersion, NoVersionFound, UnresolvedPlaceholder
from .rewrite import DriverArg, _global_span, _resolve_driver, _splice
from .tokens import VersionToken


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


def _scan_candidate_values(pv: PathVersions, driver: VersionToken) -> set[int]:
    part_text, _ = pv.parts[driver.part_index]
    v_start, v_end = driver.span
    prefix = re.escape(part_text[:v_start] + driver.case)
    suffix = re.escape(part_text[v_end:])
    entry_re = re.compile(f"^{prefix}(\\d+){suffix}$")
    parent = _parent_of_part(pv, driver)
    try:
        entries = os.listdir(parent)
    except OSError:
        return set()
    found: set[int] = set()
    for entry in entries:
        m = entry_re.match(entry)
        if not m:
            continue
        digits = m.group(1)
        value = int(digits)
        if digits != f"{value:0{driver.pad}d}":
            continue
        found.add(value)
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


def list_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[int]:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, group = _driver_and_group(pv, driver)
    candidates = _scan_candidate_values(pv, driver_token)
    if not candidates:
        return []
    result: list[int] = []
    seen_reals: set[str] = set()
    for value in sorted(candidates):
        edits = [(*_global_span(pv, t), t.format(value)) for t in group]
        candidate_path = _splice(pv.path, edits)
        if not os.path.exists(candidate_path):
            continue
        is_link = os.path.islink(candidate_path)
        if is_link and not include_symlinks:
            continue
        real = os.path.realpath(candidate_path)
        if real in seen_reals:
            continue
        seen_reals.add(real)
        result.append(value)
    return result


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
