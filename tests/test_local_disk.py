"""Manual sanity-check against a real path on disk.

Not a pytest test — run with:
    uv run python tests/test_local_disk.py
"""

from filever import (
    all_versions,
    config,
    discover,
    earliest_version,
    find_version,
    latest_version,
    missing_versions,
    new_version,
    next_version,
    prev_version,
    split_version,
)

FP = (
    "C:/Users/joker/trash/versionfiles/HOW_030_light_v008.max"
)


def fmt(vf) -> str:
    """One-line representation of a VersionedFile (or 'none')."""
    if vf is None:
        return "none"
    return f"{vf.version.formatted} @ {vf.path}"


def rule(label: str) -> None:
    print(f"\n--- {label} ---")


rule("discover")
pv = discover(FP)
print(f"versions on the path: {[v.formatted for v in pv.versions]}")
print(f"agrees:               {pv.agrees()}")

rule("all_versions on disk")
for vf in all_versions(pv):
    print(fmt(vf))

rule("split_version (filename only)")
prefix, token, suffix = split_version(FP)
print(f"prefix = {prefix!r}")
print(f"token  = {token.formatted}")
print(f"suffix = {suffix!r}")

rule("disk queries")
print(f"latest_version:   {fmt(latest_version(FP))}")
print(f"earliest_version: {fmt(earliest_version(FP))}")
print(f"next_version:     {fmt(next_version(FP))}")
print(f"prev_version:     {fmt(prev_version(FP))}")
print(f"new_version:      {fmt(new_version(FP))}")
print(f"missing_versions: {missing_versions(FP)}")

rule("is FP the latest?")
# Approach A — cleanest: next_version returns None only when the current IS the latest.
is_latest_a = next_version(FP) is None
print(f"via next_version is None: {is_latest_a}")

# Approach B — compare integer values. Works even without disk access to the current.
current_token = find_version(FP)
latest_vf = latest_version(FP)
is_latest_b = latest_vf is not None and current_token.value == latest_vf.version.value
print(f"via value comparison:     {is_latest_b}")

# Approach C — direct VersionedFile equality. Works, but fragile: relies on Path
# comparison being reflexive (separator/case sensitivity varies by OS).
from pathlib import Path  # noqa: E402
current_vf_like = latest_vf and latest_vf.path == Path(FP)
print(f"via VersionedFile path equality (fragile): {bool(current_vf_like)}")

rule("latest -> new_version (the 'open latest, save-as next' flow)")
# Common pipeline pattern: find the latest existing version, then get the next
# unwritten slot to save into.
latest = latest_version(FP)
fresh = new_version(FP)
print(f"latest existing: {fmt(latest)}")
print(f"next free slot:  {fmt(fresh)}")
print(f"next free path exists on disk? {fresh.path.exists()}")

rule("loose pad mode (config.strict_pad = False)")
# Strict mode (default) only surfaces entries whose pad matches the seed's
# formatter output. Loose mode surfaces every v\d+ entry regardless of pad —
# useful for projects that mix v01, v006, v0010 styles on disk.
config.strict_pad = False
print(f"config.strict_pad = {config.strict_pad}")
for vf in all_versions(FP):
    print(f"  pad={vf.version.pad}  {fmt(vf)}")
print(f"latest_version (loose): {fmt(latest_version(FP))}")
print(f"new_version   (loose):  {fmt(new_version(FP))}  <- still uses seed pad")
config.strict_pad = True  # reset so script re-runs are deterministic
