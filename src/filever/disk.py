from __future__ import annotations

import glob
import os
import re
from collections.abc import Callable
from pathlib import Path

from . import config
from .discover import PathVersions, discover
from .errors import AmbiguousVersion, NoVersionFound, UnresolvedPlaceholder
from .rewrite import DriverArg, _global_span, _resolve_driver, _splice, set_version
from .tokens import PlaceholderToken, VersionedFile, VersionToken


def _to_pv(pv_or_path: PathVersions | str) -> PathVersions:
    if isinstance(pv_or_path, PathVersions):
        return pv_or_path
    return discover(pv_or_path)


def _check_no_placeholders(pv: PathVersions) -> None:
    """Refuse placeholders in folder parts.

    Filename-position placeholders (####, %04d) are allowed — they're the
    frame token of a sequence, and disk operations glob-expand them.
    """
    filename_idx = pv.filename_index
    bad = [p for p in pv.placeholders if p.part_index != filename_idx]
    if bad:
        raise UnresolvedPlaceholder(
            "disk operations require resolved folder parts "
            f"(no #### or %0Nd inside folder names): {pv.path!r}"
        )


def _placeholder_to_glob(placeholder: PlaceholderToken) -> str:
    """Convert a filename-position PlaceholderToken to a digit-only glob pattern."""
    return "[0-9]" * placeholder.width


def _exists_with_globbing(candidate_path: str, pv: PathVersions) -> bool:
    """True if candidate_path resolves to at least one real file.

    When the seed's filename contains fileseq-style placeholders (####, %04d),
    they're replaced with digit-only glob classes and glob.glob is used.
    Otherwise falls back to os.path.exists (unchanged behaviour).
    """
    filename_idx = pv.filename_index
    fname_holders = [p for p in pv.placeholders if p.part_index == filename_idx]
    if not fname_holders:
        return os.path.exists(candidate_path)
    pattern = candidate_path
    for ph in fname_holders:
        pattern = pattern.replace(ph.raw, _placeholder_to_glob(ph), 1)
    return bool(glob.glob(pattern))


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


def _scan_candidate_entries(
    pv: PathVersions, driver: VersionToken
) -> dict[int, tuple[str, int]]:
    """Return {value: (entry_name, entry_pad)} for entries matching the driver pattern.

    entry_pad is always the literal digit count of the on-disk entry — v1000 is
    pad 4, v01 is pad 2, v006 is pad 3. No inference, no cleverness.

    In strict mode (config.strict_pad=True, default), only entries whose digits
    equal f"{value:0{driver.pad}d}" are included (natural pad-overflow like
    v1000 from pad 3 still passes because the format output matches).

    In loose mode (config.strict_pad=False), entries of any digit width are
    included. On value collision (same value, different pad), the entry whose
    pad matches driver.pad wins; otherwise first-alphabetically.
    """
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
    strict = config.strict_pad
    found: dict[int, tuple[str, int]] = {}
    for entry in sorted(entries):
        m = entry_re.match(entry)
        if not m:
            continue
        digits = m.group(1)
        value = int(digits)
        entry_pad = len(digits)
        if strict and digits != f"{value:0{driver.pad}d}":
            continue
        if value not in found or (
            entry_pad == driver.pad and found[value][1] != driver.pad
        ):
            found[value] = (entry, entry_pad)
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
    entry_pad: int | None = None,
) -> VersionedFile:
    pad = entry_pad if entry_pad is not None else driver_token.pad
    new_raw = f"{driver_token.case}{value:0{pad}d}"
    span_start = driver_token.span[0]
    new_token = VersionToken(
        raw=new_raw,
        value=value,
        pad=pad,
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
    exists: Callable[[str], bool] | None = None,
) -> list[VersionedFile]:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, group = _driver_and_group(pv, driver)
    candidates = _scan_candidate_entries(pv, driver_token)
    if not candidates:
        return []
    driver_part_text, driver_part_offset = pv.parts[driver_token.part_index]
    driver_part_end = driver_part_offset + len(driver_part_text)
    check_exists = exists if exists is not None else lambda p: _exists_with_globbing(p, pv)
    # When the filename holds a placeholder the candidate_path itself is a glob
    # template, not a real file — so probe the driver's part on disk for symlink
    # status instead.
    has_filename_placeholder = any(
        p.part_index == pv.filename_index for p in pv.placeholders
    )
    result: list[VersionedFile] = []
    seen_reals: set[str] = set()
    for value in sorted(candidates):
        entry_name, entry_pad = candidates[value]
        driver_edit = (driver_part_offset, driver_part_end, entry_name)
        other_edits = [
            (*_global_span(pv, t), t.format(value)) for t in group if t is not driver_token
        ]
        candidate_path = _splice(pv.path, [driver_edit, *other_edits])
        if not check_exists(candidate_path):
            continue
        link_probe = (
            os.path.normpath(_parent_of_part(pv, driver_token) + "/" + entry_name)
            if has_filename_placeholder
            else candidate_path
        )
        is_link = os.path.islink(link_probe)
        if is_link and not include_symlinks:
            continue
        real = os.path.realpath(link_probe)
        if real in seen_reals:
            continue
        seen_reals.add(real)
        result.append(_make_versioned_file(candidate_path, value, driver_token, entry_pad))
    return result


def _list_on_disk(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> list[int]:
    return [
        vf.version.value
        for vf in all_versions(
            pv_or_path, driver=driver, include_symlinks=include_symlinks, exists=exists
        )
    ]


def latest_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> VersionedFile | None:
    results = all_versions(
        pv_or_path, driver=driver, include_symlinks=include_symlinks, exists=exists
    )
    return max(results, key=lambda v: v.version.value) if results else None


def earliest_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> VersionedFile | None:
    results = all_versions(
        pv_or_path, driver=driver, include_symlinks=include_symlinks, exists=exists
    )
    return min(results, key=lambda v: v.version.value) if results else None


def next_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> VersionedFile | None:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    higher = [
        v for v in all_versions(pv, driver=driver, include_symlinks=include_symlinks, exists=exists)
        if v.version.value > current
    ]
    return min(higher, key=lambda v: v.version.value) if higher else None


def prev_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> VersionedFile | None:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    current = driver_token.value
    lower = [
        v for v in all_versions(pv, driver=driver, include_symlinks=include_symlinks, exists=exists)
        if v.version.value < current
    ]
    return max(lower, key=lambda v: v.version.value) if lower else None


def new_version(
    pv_or_path: PathVersions | str,
    *,
    driver: DriverArg = None,
    include_symlinks: bool = False,
    exists: Callable[[str], bool] | None = None,
) -> VersionedFile:
    pv = _to_pv(pv_or_path)
    _check_no_placeholders(pv)
    driver_token, _ = _driver_and_group(pv, driver)
    existing = _list_on_disk(
        pv, driver=driver, include_symlinks=include_symlinks, exists=exists
    )
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
    exists: Callable[[str], bool] | None = None,
) -> list[int]:
    existing = set(
        _list_on_disk(pv_or_path, driver=driver, include_symlinks=include_symlinks, exists=exists)
    )
    if not existing:
        return []
    return [v for v in range(min(existing), max(existing) + 1) if v not in existing]
