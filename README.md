# filever

Discover, parse, and manipulate `v`-prefixed version numbers in filesystem paths. Sibling to `fileseq` — `fileseq` handles frames, `filever` handles versions.

## Install

```bash
uv add filever
```

## Quick filename queries

For simple cases where you just need the version from a filename:

```python
from filever import find_version, has_version, split_version

find_version("char_geo_v015.abc")          # VersionToken(value=15, pad=3, ...)
find_version("untitled.abc")               # None
has_version("char_geo_v015.abc")           # True

token = find_version("char_geo_v015.abc")
token.formatted                            # 'v015'
token.value                                # 15

prefix, token, suffix = split_version("char_geo_v015.abc")
# prefix='char_geo_', token=VersionToken(...), suffix='.abc'
prefix + token.formatted + suffix          # 'char_geo_v015.abc'
```

`find_version` and friends examine only the filename segment — folder version tokens are ignored. Use `discover()` when you need the full picture.

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
from filever import all_versions, latest_version, earliest_version
from filever import next_version, prev_version, new_version, missing_versions

seed = "/publish/v015/model/char_geo_v015.abc"

all_versions(seed)                # [VersionedFile(v015), VersionedFile(v016), ...]
latest_version(seed).version.value    # 20
earliest_version(seed).version.value  # 15
next_version(seed).version.value      # 16  (closest existing above current)
prev_version(seed)                    # None  (nothing below v015)
new_version(seed).version.value       # 21  (latest + 1, does not exist yet)
missing_versions(seed)                # [18, 19]  (gaps in the sequence)
```

Disk scans use the **shallowest** version-bearing part as the anchor. For a path like `/projects/assets/character_v003.mp4` (version only in filename), it lists siblings in the same directory. Symlinks are skipped by default; pass `include_symlinks=True` to include them (deduped against real targets).

### `VersionedFile` — full path + version token

All disk functions return `VersionedFile` objects carrying both the reconstructed path and the version token:

```python
from filever import all_versions, discover

pv = discover("/publish/v015/model/char_geo_v015.abc")
for vf in all_versions(pv):
    print(f"{vf.version.formatted} → {vf.path}")
```

```
v015 → /publish/v015/model/char_geo_v015.abc
v016 → /publish/v016/model/char_geo_v016.abc
v017 → /publish/v017/model/char_geo_v017.abc
v020 → /publish/v020/model/char_geo_v020.abc
```

### `new_version` — the next save slot

`new_version` finds the highest version on disk and proposes `latest + 1`. The returned `VersionedFile` is guaranteed **not** to exist yet — it's the path to write to next:

```python
vf = new_version("/publish/v015/model/char_geo_v015.abc")
vf.version.value      # 21  (because v020 is latest on disk)
vf.version.formatted  # 'v021'
vf.path               # PosixPath('/publish/v021/model/char_geo_v021.abc')
vf.path.exists()      # False
```

### Sequences — using `####` or `%04d` in the frame position

When your file is one frame of an image sequence, different versions often cover different frame ranges — v015 might start at frame 1005 while v001 started at 1001. A literal frame in the seed asks "does this exact frame exist in each version?" and silently misses versions that don't have it.

Replace the frame with a fileseq-style placeholder (`####` or `%04d`) to switch to sequence-aware existence: any frame in that version counts.

```python
from filever import all_versions, latest_version, new_version

seed = "/render/HOW_030/v001/beauty.####.exr"

for vf in all_versions(seed):
    print(f"{vf.version.formatted} → {vf.path}")
# v001 → /render/HOW_030/v001/beauty.####.exr
# v002 → /render/HOW_030/v002/beauty.####.exr
# v015 → /render/HOW_030/v015/beauty.####.exr    ← now visible even if frames start at 1005
# v020 → /render/HOW_030/v020/beauty.####.exr
```

The returned `VersionedFile.path` keeps the placeholder — hand it straight to `fileseq` to enumerate frames:

```python
import fileseq
for vf in all_versions(seed):
    seq = fileseq.findSequenceOnDisk(str(vf.path))
    print(f"{vf.version.formatted}: {seq.frameRange()}")
# v001: 1001-1100
# v015: 1005-1150
# v020: 1010-1200
```

Concrete frame numbers still work — they just keep exact-frame semantics:

```python
all_versions("/render/HOW_030/v001/beauty.1001.exr")   # only versions with frame 1001
all_versions("/render/HOW_030/v001/beauty.####.exr")   # any version whose sequence exists
```

Placeholders in **folder** parts remain rejected (they have no sequence meaning):

```python
all_versions("/render/v###/beauty.####.exr")   # raises UnresolvedPlaceholder
```

### `exists=` — custom existence semantics

If you need something other than filesystem `os.path.exists` / glob (a companion metadata file, a database check, a remote store), pass an `exists=` callable. It receives the reconstructed path and returns a bool.

```python
from pathlib import Path

def has_publish_marker(path: str) -> bool:
    return (Path(path).parent / "publish.json").exists()

for vf in all_versions(seed, exists=has_publish_marker):
    print(vf.version.formatted)   # only versions that have a publish.json
```

`exists=` works on every disk function (`latest_version`, `new_version`, etc.).

### `pv.versions` vs disk queries

`pv.versions` and the disk-scan functions answer *different* questions. `pv.versions` reports what version tokens appear inside the single path string you gave it — no filesystem access. The disk functions read the filesystem and report which versions of the asset actually exist there.

| Question | Use |
|---|---|
| What versions are written into this one filepath? | `pv.versions` |
| What versions of this asset exist on disk? | `all_versions(pv)` |
| What's the newest one on disk? | `latest_version(pv)` |
| What's the next slot to save into? | `new_version(pv)` |
| Are there gaps in the version sequence? | `missing_versions(pv)` |

## Errors

- `AmbiguousVersion` — grouped op on a mismatched path with no `driver=`.
- `NoDriverToken` — `driver="folder"` on a path that has no folder version.
- `NoVersionFound` — no `v\d+` anywhere on the path.
- `UnresolvedPlaceholder` — disk op on a path with `####` or `%03d` in a folder part. Filename-position placeholders are allowed (they enable sequence-aware scans).

All inherit from `FileverError`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

See [spec.md](spec.md) for the full behavioral specification.
