# filever — Specification Sheet

**Status:** Draft / high-level requirements
**Purpose:** A Python library for discovering, parsing, and manipulating `v`-prefixed version numbers embedded in filesystem paths. Conceptually a sibling to `fileseq` (which handles frame sequences) — `filever` handles versions.

---

## 1. Problem Statement

Version numbers appear in many places within a filepath — in folder names, in filenames, sometimes in both, sometimes matching and sometimes not. They also appear alongside frame-padding tokens (`%03d`, `####`) and unrelated digit runs (frame numbers, UDIM tiles, dates) that must not be confused with a version. No existing Python library discovers versions across path parts while distinguishing them from those other tokens.

`filever` fills that gap: given a path, it locates every `v`-prefixed version token, tells you where it lives, and lets you compare, extract, rewrite, or scan disk for related versions.

---

## 2. Scope

### In scope — pure-string / path layer (`filever`)
- Discovering `v\d+` version tokens across every part of a path (each folder segment, the filename).
- Distinguishing version tokens from frame-padding tokens (`%03d`, `####`).
- Reporting the location of each token (which path part, character span).
- Comparing versions and identifying matches/mismatches across path parts.
- Bumping / rewriting a version and returning a new path, preserving pad width and letter case.

### In scope — disk-aware layer (`filever.disk` or equivalent submodule)
- Enumerating versions that exist on disk for a given path (list / latest / earliest / previous / next).
- Grouped scans that treat locked (matching) version tokens as a single logical version.
- A `driver=` selector for mismatched paths — see §6.

### Out of scope (at least for v1)
- Expanding frame ranges or enumerating sequences on disk — that's `fileseq`'s job.
- Recognizing semver (`1.4.2`), bare integers (`1001`), UDIM tiles, dates, or any non-`v\d+` notation as versions. These may appear in paths; filever ignores them.
- Defining a version-comparison standard beyond integer ordering of the digit portion.

The two layers are separated so callers who don't need disk I/O don't pay for it, and so the pure layer stays trivially testable.

---

## 3. Core Constraints & Rules

1. **One version per path part.** Within any single path segment, at most one token is treated as *the* version. When multiple `v\d+` tokens exist within one part (`char_v001_v002.png`), the **rightmost** wins by default. Callers may opt into leftmost or "surface all candidates" behavior.
2. **Path parts are independent.** A version in a folder and a version in the filename are separate tokens. They may match or mismatch; the library reports both plus whether they agree. Two tokens agree only when both integer value **and** pad width are equal — `v1` and `v01` do **not** agree.
3. **Notation preservation on rewrite.** Bumping `v003` yields `v004`. Zero-padding width is preserved (`v9 → v10` widens naturally; `v009 → v010` stays 3-wide). Letter case is preserved (`V002 → V003`, never normalized).
4. **Non-destructive.** Operations return new strings/objects; inputs are never mutated.
5. **Ambiguity is surfaced, not guessed.** When operating across parts with mismatched versions, disk-scanning and grouped rewrites raise or require an explicit `driver=` rather than silently picking a winner.
6. **A path part is scanned as a whole string.** The regex operates on the full segment including extension (e.g. `v001.png` matches — the trailing `.` is a valid right boundary). Implementers should not pre-split the extension.

---

## 4. Recognized Tokens

Only two token classes matter to filever:

| Token class | Regex | Example | Notes |
|---|---|---|---|
| **Version token** | `(?<![A-Za-z0-9])[vV](\d+)(?![A-Za-z0-9])` | `v003`, `V002`, `v10` | Case-insensitive match. Preserve original case and pad width on rewrite. The bounded regex ensures `versionv001`, `MOV3D`, and `v001a` do not match; `v001`, `_v001_`, `v001.png` do. |
| **Frame placeholder** | `%0\d+d` or `#+` | `%03d`, `####` | A *template* token, not a concrete version. Report width (`%03d` → 3; `####` → 4). Callers may want to list these separately or ignore them. |

Everything else that looks numeric — semver (`1.4.2`), bare integers (`1001`, `1050`), UDIM tiles, dates (`2024-11-03`) — is **not classified as anything**. filever sees them as ordinary characters. This is deliberate: it eliminates the version-vs-frame-vs-UDIM ambiguity problem entirely.

---

## 5. Conceptual Data Model (non-binding)

The implementer chooses exact names/signatures. These are the concepts the API must expose:

- **VersionToken** — a single discovered version. Carries: the raw matched text (`"v003"`), the parsed integer value (`3`), the pad width (`3`), the letter case of the prefix (`"v"` or `"V"`), the path-part it belongs to, its index among path parts, and its character span within that part.
- **PlaceholderToken** — a frame-padding token. Carries: the raw text (`"%03d"`, `"####"`), the notation (`"printf"` or `"hash"`), the width, and its location (path-part index + span).
- **PathVersions** — the result of analyzing a full path. Carries: the ordered collection of `VersionToken`s and `PlaceholderToken`s, convenience access to "the folder version(s)" vs "the filename version", a boolean for whether the version tokens agree across parts, and the set of distinct version values on the path (the "version group" — see §6).
- **TokenClass** — an enumeration: `VERSION`, `PLACEHOLDER`.

---

## 6. Required Capabilities (behavioral)

The implementer decides the surface, but these behaviors must be reachable.

### Pure-string layer

- **Discover** — given a path, return all version tokens and placeholder tokens with their locations.
- **Locate** — for any token, report which path part and character span it occupies.
- **Classify** — for any token, report its class (version vs placeholder) and, for versions, its integer value and pad width.
- **Compare** — given two version tokens (or two integer values), determine ordering / equality.
- **Match-check** — for a path with versions in multiple parts, report whether they agree and which parts disagree.
- **Bump (single-token)** — shift one specific token's version by any integer delta (`by=1` default; negative values shift down), preserving pad width and letter case, returning the updated token/path.
- **Rewrite (single-token)** — produce a new path string with one chosen token replaced, leaving all other parts untouched.
- **Grouped rewrite** — replace *every* token on the path whose current value matches a given source value. Used when the caller wants folder-and-file to move in lockstep. Default behavior when all version tokens on a path already agree.
- **Filter** — retrieve only version tokens, or only placeholder tokens, as the caller requests.

### Disk-aware layer

- **List** — return the sorted set of versions that exist on disk for a given path. Symlinks are skipped by default; `include_symlinks=True` opts in and dedupes against their real targets so a `latest → v017` symlink does not double-count.
- **Latest / Earliest** — max / min of that set.
- **Previous / Next (on disk)** — the closest existing version below / above the current, or `None`.
- **Increment / Decrement** — current ± 1, without touching the filesystem. (Same as `Next`/`Previous` but with an `exists=False` flag or a distinct method.)

### The `driver=` selector

Grouped operations (disk scan, grouped rewrite) treat **all version tokens on the path as a single group** — they move together, they're scanned together. Whenever the tokens agree, this is the only behavior available. There is no API for intentionally splitting a matching group; if the caller wants that, they must first mutate the path so the tokens disagree.

When tokens disagree (e.g. `/cache/v5/textures/wood_v2_diffuse.tga`), grouped operations **raise** `AmbiguousVersion` unless the caller specifies `driver=`.

- `driver="folder"` / `driver="filename"` / `driver=<token>` — picks which token drives the scan or rewrite. The token form accepts a `VersionToken` obtained from `discover()`, for programmatic callers that already hold a specific token.
- Non-driver tokens are frozen as literals for the scan. Example: `driver="folder"` on the path above enumerates `/cache/v*/textures/wood_v2_diffuse.tga` — the filename's `v2` stays literally `v2`.
- `driver=` is meaningful only on mismatched paths. On a matching path it is ignored (the group behavior is already unambiguous).
- If `driver=` names a token class that isn't present on the path (e.g. `driver="folder"` when no folder-side version exists), the operation raises `NoDriverToken`. Silent degradation to single-part scan is not offered.

### Scan semantics (informative)

For a disk scan, the algorithm is:

1. Identify the driver token (explicit or inferred from the matched group).
2. Enumerate candidate values by listing the driver's parent directory with `v\d+` wildcarded.
3. For each candidate N, construct the full rewritten path (grouped rewrite when tokens agreed; single-token rewrite when a driver was specified).
4. Include N in the result only if the fully rewritten path exists on disk.

Step 4 is what distinguishes "list on disk" from "list observed in this one directory" — a version whose folder exists but whose file was never published does not count.

### Error taxonomy

The library exposes a small, stable set of named exceptions so callers can react precisely:

- `FileverError` — base class for everything below.
- `NoVersionFound` — a call that required at least one version token found none on the path.
- `AmbiguousVersion` — a grouped operation was invoked on a path whose version tokens disagree, and no `driver=` was supplied.
- `NoDriverToken` — `driver=` was supplied but names a token class that does not exist on the path.
- `UnresolvedPlaceholder` — a disk-layer call was given a path whose non-version parts still contain unresolved `%0Nd` / `####` templates.

---

## 7. Interop & Dependencies

- **Standard library only** — `pathlib`, `re`, `enum`, `os` (for the disk layer). No third-party deps in v1.
- **`fileseq` / `pyseq`** — no dependency, but the placeholder-token shapes (`%0Nd`, `#`) are the same tokens those libraries expand, so a caller can hand filever's placeholder output to `fileseq` for frame enumeration if they want.
- **No `packaging.version` dependency.** Since version comparison is just integer ordering on the digit portion, there's nothing to delegate.

---

## 8. Test Corpus

Fixtures below. Expected version tokens use the boundary rule from §4 (case-insensitive `[vV]\d+`, non-alphanumeric or path-boundary on both sides) and the rightmost-wins tiebreaker from §3.

| Path | Version tokens | Placeholders | Group agrees? |
|---|---|---|---|
| `/projects/v2/assets/character_v003.png` | folder `v2` (val 2, pad 1), file `v003` (val 3, pad 3) | — | no |
| `/renders/2024/shot_010/comp_v012.exr` | file `v012` | — | n/a (single) |
| `/lib/python3.11/site-packages/tool_v1.py` | file `v1` | — | n/a |
| `/sequences/sq050/sh0100/render_%03d.jpg` | — | `%03d` (w3) | n/a |
| `/build/release-1.4.2/binary_1.4.2.exe` | — | — | n/a |
| `/cache/v5/textures/wood_v2_diffuse.tga` | folder `v5`, file `v2` | — | no |
| `/frames/scene01/frame_####.png` | — | `####` (w4) | n/a |
| `/v10/output/final_v10.mov` | folder `v10`, file `v10` | — | yes |
| `/app/2.0/config/settings_v1.json` | file `v1` | — | n/a |
| `/shots/sh020/plate_v001.####.dpx` | file `v001` | `####` (w4) | n/a |
| `/data/version_3/dataset_v3.csv` | file `v3` (folder `version_3` has no `v\d+` boundary match) | — | n/a |
| `/mnt/v001/comp/beauty_1001.exr` | folder `v001` (`1001` is not classified) | — | n/a |
| `/publish/v015/model/char_geo_v012.abc` | folder `v015`, file `v012` | — | no |
| `/tools/blender-4.1/addon_%04d.py` | — | `%04d` (w4) | n/a |
| `/anim/sq010_sh0050/anim_v7.blend` | file `v7` | — | n/a |
| `/releases/v2.1.0/notes_v2.txt` | folder `v2` (bounded by `/` and `.`), file `v2` | — | yes |
| `/assets/prop_v009/lod_v2.fbx` | folder `v9`, file `v2` | — | no |
| `/publish/v015/model/char_geo_v015.abc` | folder `v015`, file `v015` | — | yes |
| `/publish/char_geo_v015/model/char_geo_v015.abc` | folder `v015`, file `v015` | — | yes |
| `char_v001_v002.png` (rightmost-wins) | file `v002` | — | n/a |
| `V002/render.exr` (case-insensitive match, case preserved on rewrite) | folder `V002` | — | n/a |

Behaviors worth asserting alongside the table:

- Rewriting `V002` up by one yields `V003`, not `v003`.
- Rewriting `v9` up by one yields `v10` (width grows naturally).
- Rewriting `v009` up by one yields `v010` (width preserved).
- Bumping `v005` by `3` yields `v008`; by `-2` yields `v003`.
- Rewriting the folder `v2.1.0` up by one yields `v3.1.0` — only the matched span (`v2`) changes; the trailing `.1.0` is untouched.
- A path like `/publish/v01/model/char_geo_v1.abc` reports **disagreement** (integer values match but pads differ), so grouped operations raise without a `driver=`.
- Grouped rewrite on `/publish/v015/model/char_geo_v015.abc` from 15 to 17 yields `/publish/v017/model/char_geo_v017.abc`.
- Grouped operations on `/cache/v5/textures/wood_v2_diffuse.tga` raise `AmbiguousVersion` without `driver=`; with `driver="folder"` they enumerate `/cache/v*` and freeze `wood_v2_diffuse.tga`.
- Disk scan with `driver="folder"` on a path whose folder part has no version raises `NoDriverToken`.
- Disk scan on `/render_%03d.jpg` raises `UnresolvedPlaceholder`; caller must resolve the frame token first.

---

## 9. Open Questions

None remaining at spec level. All prior questions are resolved below.

### Closed

- **Rewrite addressing** — matching paths always move as a group; mismatching paths use `driver=` (folder / filename / token reference). No separate `target=` parameter, no index-based addressing.
- **Case normalization opt-in** — case is preserved on rewrite; no `normalize_case=` parameter is exposed. Pipelines that want a house style enforce it themselves.
- **Discovery ordering** — path order (left-to-right across parts) is the default return order. `PathVersions` also exposes grouped-by-part convenience access (see §5).
- **Path input types** — accept `str`, `os.PathLike`, `pathlib.Path` uniformly. On Windows, normalize backslashes to forward slashes internally for parsing, preserve the input's original separator style on output (`C:\publish\v015\char.abc` in yields `C:\publish\v016\char.abc` out).
- **PyPI naming** — `filever` is the working title; verify availability at publish time. No design impact.
- **Bare integer default (version / frame / ambiguous)** — bare integers are not versions, ever.
- **Semver bump semantics** — semver is not a filever notation.
- **Version-vs-UDIM disambiguation** — UDIM is not a filever notation.
- **Pad-width equality in match-check** — pad width is part of agreement; `v1` and `v01` do not agree.
- **Bump by N vs by 1** — `by` accepts any integer, defaults to `1`.
- **`driver=` on missing token** — raises `NoDriverToken`.
- **`driver=` on matching path** — ignored (grouped behavior already unambiguous).
- **Symlinks in disk scan** — skipped by default, `include_symlinks=True` opts in with dedupe against real targets.

---

## 10. Naming

Working module name: **`filever`** — chosen to parallel `fileseq`. Import should read naturally (`from filever import discover`, etc.). Verify no PyPI collision before release.

---

### Scratch notes

Original end-use cases, mapped to §6:

- what's the version number → Discover → `VersionToken.value`
- version string → Discover → `VersionToken.raw`
- padding → Discover → `VersionToken.pad`
- list of versions on disk → Disk.List
- latest / earliest on disk → Disk.Latest / Disk.Earliest
- previous / next on disk → Disk.Previous / Disk.Next
- increment / decrement without disk check → Disk.Next / Disk.Previous with `exists=False`, or a distinct Increment / Decrement method

On forcing resolved (non-placeholder) paths as input: the pure layer accepts anything — placeholders and versions coexist happily. The **disk layer** should refuse paths whose non-version parts still contain unresolved placeholders (`####`, `%0Nd`), since it can't stat a template. Callers are expected to resolve those to a concrete frame (typically the lowest) before scanning for versions.
