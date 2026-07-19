# filever

Discover, parse, and manipulate `v`-prefixed version numbers in filesystem paths. Sibling to `fileseq` — `fileseq` handles frames, `filever` handles versions.

## Install

```bash
uv add filever
```

## Discover

```python
from filever import discover

pv = discover("/publish/v015/model/char_geo_v015.abc")
pv.versions           # (VersionToken(v015, part 1), VersionToken(v015, part 3))
pv.agrees()           # True
pv.folder_versions    # (VersionToken(v015),)
pv.filename_version   # VersionToken(v015)
```

### `pv.agrees()`

Returns `True` if every version token on the path shares the same value **and** the same pad width. This is how you detect whether the folder-side and filename-side versions are locked together — a mismatch usually means someone bumped one but not the other.

```python
discover("/publish/v015/model/char_geo_v015.abc").agrees()   # True  — both v015
discover("/publish/v015/model/char_geo_v012.abc").agrees()   # False — 15 vs 12
discover("/publish/v01/model/char_geo_v1.abc").agrees()      # False — pads differ (2 vs 1)
discover("/renders/2024/shot_010/comp_v012.exr").agrees()    # True  — only one token
discover("/frames/scene01/frame_####.png").agrees()          # True  — no versions
```

`bump`, `set_version`, and the disk-scan calls all use this internally: when it's `True` they operate on the whole group in lockstep; when it's `False` they raise `AmbiguousVersion` unless you pass a `driver=`.

## Bump & rewrite

```python
from filever import bump, set_version

bump("char_v001.png")                                        # 'char_v002.png'
bump("char_v009.png")                                        # 'char_v010.png'   (width grows)
bump("char_V002.png")                                        # 'char_V003.png'   (case preserved)
bump("char_v005.png", by=3)                                  # 'char_v008.png'
bump("/publish/v015/model/char_geo_v015.abc")                # both tokens move
# → '/publish/v016/model/char_geo_v016.abc'

set_version("/publish/v015/model/char_geo_v015.abc", 42)
# → '/publish/v042/model/char_geo_v042.abc'
```

## Mismatched paths need a `driver`

```python
from filever import bump, AmbiguousVersion

path = "/cache/v5/textures/wood_v2_diffuse.tga"

bump(path)                        # raises AmbiguousVersion
bump(path, driver="folder")       # '/cache/v6/textures/wood_v2_diffuse.tga'
bump(path, driver="filename")     # '/cache/v5/textures/wood_v3_diffuse.tga'
```

## Scan disk for versions

```python
from filever.disk import list_on_disk, latest_on_disk, next_version, previous_version

seed = "/publish/v015/model/char_geo_v015.abc"

list_on_disk(seed)                    # [15, 16, 17, 20]
latest_on_disk(seed)                  # 20
next_version(seed)                    # 16  (closest existing above)
previous_version(seed)                # None
next_version(seed, exists=False)      # 16  (just current + 1, no disk check)
```

Disk scans use the **shallowest** version-bearing part as the anchor. For a path like `/projects/assets/character_v003.mp4` (version only in filename), it lists siblings in the same directory. Symlinks are skipped by default; pass `include_symlinks=True` to include them (deduped against real targets).

## Errors

- `AmbiguousVersion` — grouped op on a mismatched path with no `driver=`.
- `NoDriverToken` — `driver="folder"` on a path that has no folder version.
- `NoVersionFound` — no `v\d+` anywhere on the path.
- `UnresolvedPlaceholder` — disk op on a path with `####` or `%03d` still present.

All inherit from `FileverError`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

See [spec.md](spec.md) for the full behavioral specification.
