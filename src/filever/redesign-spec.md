High-level breakdown of methods, organized by concern.

## Core dataclasses

- `VersionMatch` — result of parsing a filename string: `(raw: str, value: int, padding: int, span: tuple[int, int])`. The core data unit passed around everywhere.
  - `formatted` — computed property; returns the version token as a string: `f"v{value:0{padding}d}"` → e.g. `'v002'`. Primary way to get the formatted token; prefer this over calling `format_version` separately.
- `VersionedFile` — a `(path: Path, version: VersionMatch)` pairing. Does not guarantee the file exists — existence is determined by the calling function.

## Discovery / parsing

Input `name` accepts `str | Path`. When a `Path` is given, only the filename (`.name`) is examined — not the full path.

- `find_version(name: str | Path) -> VersionMatch | None` — locate the `v\d+` token in a filename. Core primitive everything else builds on.
- `find_all_versions(name: str | Path) -> list[VersionMatch]` — some names carry multiple tokens (`shot_v003_texture_v002`). Returns all matches; caller decides which is canonical.
- `has_version(name: str | Path) -> bool` — cheap boolean guard. Returns `False` if no version token is found; does not return a dataclass. Use `find_version` when you need the data.
- `parse_version(name: str | Path) -> int | None` — convenience wrapper returning just the integer value.
- `split_version(name: str | Path) -> tuple[str, VersionMatch, str]` — returns `(prefix, version, suffix)` so callers can reconstruct a name after bumping. Workhorse for rename operations.

## Scanning the filesystem

All functions here take the current file as a reference point. Functions that return `VersionedFile` instances guarantee the file exists on disk, except `new_version`.

- `discover_versions(path: str | Path, pattern=...) -> list[VersionedFile]` — given a file (or its stem), glob the directory for all siblings sharing the same prefix/suffix and collect their versions. Files exist on disk.
- `latest_version(path: str | Path) -> VersionedFile | None` — the sibling with the highest version on disk.
- `next_existing(path: str | Path) -> VersionedFile | None` — next higher version that exists on disk, relative to the given file's version.
- `prev_existing(path: str | Path) -> VersionedFile | None` — next lower version that exists on disk, relative to the given file's version.
- `new_version(path: str | Path) -> VersionedFile` — constructs a `VersionedFile` for `latest + 1`. The file does **not** exist yet; this is the proposed save path. Use `.version.value` or `.version.formatted` to read the version from the result.
- `missing_versions(path: str | Path) -> list[int]` — gaps in the sequence; useful for pipeline integrity checks.

## Manipulation / formatting

- `bump(name: str | Path, by: int = 1) -> str` — return a new name with an incremented version, preserving zero-padding (`v012` → `v013`). Makes no existence guarantee — the result may already exist on disk.
- `set_version(name: str | Path, n: int) -> str` — force a specific version number.
- `format_version(n: int, padding: int = 3) -> str` — int → `v###`. Secondary utility for cases where you have a bare int and no `VersionMatch`; prefer `VersionMatch.formatted` otherwise.

## Open design questions

1. **Padding policy** — preserve source padding per-file, or enforce a pipeline-wide width? Studios usually standardize (e.g. always `v###`), but legacy `v0001` files are common.
2. **Multiple tokens** — when `find_version` is called on a name with multiple tokens, which wins: leftmost, rightmost, or an explicit index? A named-group pattern per file type is often cleaner than a heuristic.
3. **Case & separators** — match `V\d+` too? Require a word boundary (`_v012_`) to avoid false matches in words like `conv12`?

--- 

# Things I'd like to keep design element wise

## Mismatched paths need a `driver`

```python
from filever import bump, AmbiguousVersion

path = "/cache/v5/textures/wood_v2_diffuse.tga"

bump(path)                        # raises AmbiguousVersion
bump(path, driver="folder")       # '/cache/v6/textures/wood_v2_diffuse.tga'
bump(path, driver="filename")     # '/cache/v5/textures/wood_v3_diffuse.tga'
```

Disk scans use the **shallowest** version-bearing part as the anchor. For a path like `/projects/assets/character_v003.mp4` (version only in filename), it lists siblings in the same directory. Symlinks are skipped by default; pass `include_symlinks=True` to include them (deduped against real targets).

_VERSION_RE = re.compile(r"(?<![A-Za-z0-9])([vV])(\d+)(?![A-Za-z0-9])")

It should support all the filepaths of files and/or folders as mentioned in the existing repo. Which takes into account sync versions on the filename and or folder parts within the same path and the driver feature, as needed. Where users can specify which one to control