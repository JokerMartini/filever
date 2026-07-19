from __future__ import annotations

from .discover import PathVersions, discover
from .errors import AmbiguousVersion, NoDriverToken, NoVersionFound
from .tokens import VersionToken

DriverArg = str | VersionToken | None


def _resolve_driver(pv: PathVersions, driver: DriverArg) -> VersionToken:
    if isinstance(driver, VersionToken):
        for v in pv.versions:
            if v.part_index == driver.part_index and v.span == driver.span and v.raw == driver.raw:
                return v
        raise NoDriverToken(f"driver token {driver.raw!r} not found on path {pv.path!r}")
    if driver == "folder":
        folders = pv.folder_versions
        if not folders:
            raise NoDriverToken(f"driver='folder' but path has no folder version: {pv.path!r}")
        return folders[-1]
    if driver == "filename":
        fname = pv.filename_version
        if fname is None:
            raise NoDriverToken(f"driver='filename' but path has no filename version: {pv.path!r}")
        return fname
    raise ValueError(
        f"driver must be 'folder', 'filename', a VersionToken, or None; got {driver!r}"
    )


def _select_group(pv: PathVersions, driver: DriverArg) -> list[VersionToken]:
    if not pv.versions:
        raise NoVersionFound(f"no version tokens on path: {pv.path!r}")
    if driver is not None:
        _resolve_driver(pv, driver)
    if pv.agrees():
        return list(pv.versions)
    if driver is None:
        raise AmbiguousVersion(
            f"path has mismatched version tokens and no driver= supplied: {pv.path!r}"
        )
    lead = _resolve_driver(pv, driver)
    return [v for v in pv.versions if v.value == lead.value and v.pad == lead.pad]


def _global_span(pv: PathVersions, token: VersionToken) -> tuple[int, int]:
    _part_text, part_offset = pv.parts[token.part_index]
    start, end = token.span
    return part_offset + start, part_offset + end


def _splice(path: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, _text in edits:
        if start < 0 or end > len(path) or start > end:
            raise ValueError(
                f"invalid splice range: ({start}, {end}) in path of length {len(path)}"
            )
    edits_sorted = sorted(edits, key=lambda e: e[0], reverse=True)
    out = path
    for start, end, text in edits_sorted:
        out = out[:start] + text + out[end:]
    return out


def rewrite_token(pv: PathVersions, token: VersionToken, new_value: int) -> str:
    if new_value < 0:
        raise ValueError(f"new_value must be non-negative, got {new_value}")
    start, end = _global_span(pv, token)
    return _splice(pv.path, [(start, end, token.format(new_value))])


def set_version(
    pv_or_path: PathVersions | str,
    value: int,
    *,
    driver: DriverArg = None,
) -> str:
    pv = pv_or_path if isinstance(pv_or_path, PathVersions) else discover(pv_or_path)
    group = _select_group(pv, driver)
    edits = [(*_global_span(pv, t), t.format(value)) for t in group]
    return _splice(pv.path, edits)


def bump(
    pv_or_path: PathVersions | str,
    by: int = 1,
    *,
    driver: DriverArg = None,
) -> str:
    pv = pv_or_path if isinstance(pv_or_path, PathVersions) else discover(pv_or_path)
    group = _select_group(pv, driver)
    lead = group[0]
    new_value = lead.value + by
    if new_value < 0:
        raise ValueError(f"bump would produce negative version: {lead.value} + {by} = {new_value}")
    edits = [(*_global_span(pv, t), t.format(new_value)) for t in group]
    return _splice(pv.path, edits)
