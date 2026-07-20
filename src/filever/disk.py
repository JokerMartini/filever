from __future__ import annotations

import os
import re
from pathlib import Path

from .discover import PathVersions, discover
from .errors import AmbiguousVersion, NoVersionFound, UnresolvedPlaceholder
from .rewrite import DriverArg, _global_span, _resolve_driver, _splice, set_version
from .tokens import VersionToken, VersionedFile


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


def _make_versioned_file(
    candidate_path: str,
    value: int,
    driver_token: VersionToken,
) -> VersionedFile:
    new_raw = driver_token.format(value)
    span_start = driver_token.span[0]
    new_token = VersionToken(
        raw=new_raw,
        value=value,
        pad=driver_token.pad,
        case=driver_token.case,
        part_index=driver_token.part_index,
        span=(span_start, span_start + len(new_raw)),
    )
    return VersionedFile(path=Path(candidate_path), version=new_token)


def all_versions(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[VersionedFile]:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, group = _driver_and_group(pv, driver)
    candidates = _scan_candidate_entries(pv, driver_token)
    if not candidates:
        return []
    driver_part_text, driver_part_offset = pv.parts[driver_token.part_index]
    driver_part_end = driver_part_offset + len(driver_part_text)
    result: list[VersionedFile] = []
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
        result.append(_make_versioned_file(candidate_path, value, driver_token))
    return result


def _list_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[int]:
    return [
        vf.version.value
        for vf in all_versions(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    ]


def latest_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> VersionedFile | None:
    results = all_versions(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    return max(results, key=lambda v: v.version.value) if results else None


def earliest_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> VersionedFile | None:
    results = all_versions(pv_or_path, driver=driver, include_symlinks=include_symlinks)
    return min(results, key=lambda v: v.version.value) if results else None


def next_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> VersionedFile | None:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    higher = [
        v for v in all_versions(pv, driver=driver, include_symlinks=include_symlinks)
        if v.version.value > current
    ]
    return min(higher, key=lambda v: v.version.value) if higher else None


def prev_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> VersionedFile | None:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    lower = [
        v for v in all_versions(pv, driver=driver, include_symlinks=include_symlinks)
        if v.version.value < current
    ]
    return max(lower, key=lambda v: v.version.value) if lower else None


def new_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> VersionedFile:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    existing = _list_on_disk(pv, driver=driver, include_symlinks=include_symlinks)
    base_value = max(existing) if existing else driver_token.value
    new_value = base_value + 1
    new_path_str = set_version(pv, new_value, driver=driver)
    new_pv = discover(new_path_str)
    token = next(
        (v for v in new_pv.versions if v.part_index == driver_token.part_index),
        None,
    )
    if token is None:
        new_raw = driver_token.format(new_value)
        span_start = driver_token.span[0]
        token = VersionToken(
            raw=new_raw,
            value=new_value,
            pad=driver_token.pad,
            case=driver_token.case,
            part_index=driver_token.part_index,
            span=(span_start, span_start + len(new_raw)),
        )
    return VersionedFile(path=Path(new_path_str), version=token)


def missing_versions(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
) -> list[int]:
    existing = set(_list_on_disk(pv_or_path, driver=driver, include_symlinks=include_symlinks))
    if not existing:
        return []
    return [v for v in range(min(existing), max(existing) + 1) if v not in existing]
