import os
from pathlib import Path

import pytest

from filever import (
    AmbiguousVersion,
    NoVersionFound,
    UnresolvedPlaceholder,
    VersionedFile,
    VersionToken,
)
from filever.disk import (
    all_versions,
    earliest_version,
    latest_version,
    missing_versions,
    new_version,
    next_version,
    prev_version,
)


@pytest.fixture
def publish_tree(tmp_path):
    base = tmp_path / "publish"
    for n in (15, 16, 17, 20):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text(f"content-{n}")
    return base


def test_all_versions_values(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = all_versions(seed)
    assert [v.version.value for v in result] == [15, 16, 17, 20]


def test_all_versions_returns_objects(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = all_versions(seed)
    assert [v.version.value for v in result] == [15, 16, 17, 20]
    assert all(isinstance(v, VersionedFile) for v in result)
    assert all(isinstance(v.version, VersionToken) for v in result)
    assert all(isinstance(v.path, Path) for v in result)
    for vf in result:
        path_str = str(vf.path)
        assert f"v{vf.version.value:03d}" in path_str
        assert path_str.endswith(f"char_geo_v{vf.version.value:03d}.abc")


def test_versioned_file_formatted(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = all_versions(seed)
    assert result[0].version.formatted == "v015"
    assert result[-1].version.formatted == "v020"


def test_latest_and_earliest(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert latest_version(seed).version.value == 20
    assert earliest_version(seed).version.value == 15


def test_latest_and_earliest_return_full_path(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    lv = latest_version(seed)
    assert isinstance(lv, VersionedFile)
    assert isinstance(lv.path, Path)
    assert str(lv.path).endswith("char_geo_v020.abc")


def test_next_version_on_disk(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert next_version(seed).version.value == 16
    seed17 = str(publish_tree / "v017" / "model" / "char_geo_v017.abc")
    assert next_version(seed17).version.value == 20


def test_prev_version_on_disk(publish_tree):
    seed = str(publish_tree / "v017" / "model" / "char_geo_v017.abc")
    assert prev_version(seed).version.value == 16


def test_next_version_no_higher(publish_tree):
    seed = str(publish_tree / "v020" / "model" / "char_geo_v020.abc")
    assert next_version(seed) is None


def test_prev_version_no_lower(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert prev_version(seed) is None


def test_new_version(publish_tree):
    """new_version returns latest_on_disk + 1 as a VersionedFile (file does not exist)."""
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = new_version(seed)
    assert isinstance(result, VersionedFile)
    # latest on disk is 20, so new should be 21
    assert result.version.value == 21
    assert not result.path.exists()


def test_new_version_with_driver(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = new_version(seed, driver="folder")
    assert result.version.value == 21


def test_new_version_no_existing_files():
    """When no siblings exist, new_version falls back to current + 1."""
    result = new_version("char_v005.png")
    assert result.version.value == 6


def test_all_versions_skips_orphaned_folder(tmp_path):
    """A folder v020 without the expected file should not appear."""
    base = tmp_path / "publish"
    for n in (15, 16):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text("")
    orphan = base / "v020" / "model"
    orphan.mkdir(parents=True)  # no file inside
    seed = str(base / "v015" / "model" / "char_geo_v015.abc")
    assert [v.version.value for v in all_versions(seed)] == [15, 16]


def test_no_versions_raises(tmp_path):
    (tmp_path / "no_version.txt").write_text("")
    with pytest.raises(NoVersionFound):
        all_versions(str(tmp_path / "no_version.txt"))


def test_placeholder_raises(tmp_path):
    with pytest.raises(UnresolvedPlaceholder):
        all_versions(str(tmp_path / "render_%03d.jpg"))


def test_ambiguous_mismatch_raises(tmp_path):
    base = tmp_path / "cache"
    (base / "v5" / "textures").mkdir(parents=True)
    (base / "v5" / "textures" / "wood_v2_diffuse.tga").write_text("")
    seed = str(base / "v5" / "textures" / "wood_v2_diffuse.tga")
    with pytest.raises(AmbiguousVersion):
        all_versions(seed)


def test_mismatch_with_driver(tmp_path):
    base = tmp_path / "cache"
    for n in (5, 6, 7):
        d = base / f"v{n}" / "textures"
        d.mkdir(parents=True)
        (d / "wood_v2_diffuse.tga").write_text("")
    seed = str(base / "v5" / "textures" / "wood_v2_diffuse.tga")
    assert [v.version.value for v in all_versions(seed, driver="folder")] == [5, 6, 7]


def test_symlink_skipped_by_default(tmp_path):
    if os.name == "nt":
        pytest.skip("symlink creation on Windows may require admin")
    base = tmp_path / "publish"
    for n in (15, 16):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text("")
    (base / "v020").symlink_to(base / "v016", target_is_directory=True)
    seed = str(base / "v015" / "model" / "char_geo_v015.abc")
    assert [v.version.value for v in all_versions(seed)] == [15, 16]
    assert [v.version.value for v in all_versions(seed, include_symlinks=True)] == [15, 16]


def test_case_strict_scan(tmp_path):
    base = tmp_path
    (base / "v015").mkdir()
    (base / "v015" / "char_V015.abc").write_text("")
    (base / "v016").mkdir()
    (base / "v016" / "char_V016.abc").write_text("")
    seed = str(base / "v015" / "char_V015.abc")
    assert [v.version.value for v in all_versions(seed)] == [15, 16]


def test_case_insensitive_surrounding_text(tmp_path):
    """Siblings with different case in the surrounding text should still match, and
    returned paths should preserve the actual on-disk casing."""
    base = tmp_path
    (base / "HOW_030_LIGHT_v001.max").write_text("")
    (base / "HOW_030_LIGHT_v002.max").write_text("")
    (base / "HOW_030_LIGHT_v003.max").write_text("")
    (base / "HOW_030_light_v010.max").write_text("")
    seed = str(base / "HOW_030_LIGHT_v003.max")
    result = all_versions(seed)
    assert [v.version.value for v in result] == [1, 2, 3, 10]
    assert str(result[3].path).endswith("HOW_030_light_v010.max")


def test_pad_strict_scan(tmp_path):
    """Sibling with different pad width should not appear."""
    base = tmp_path
    (base / "v015").mkdir()
    (base / "v015" / "seed.txt").write_text("")
    (base / "v0016").mkdir()  # different pad
    (base / "v0016" / "seed.txt").write_text("")
    (base / "v017").mkdir()
    (base / "v017" / "seed.txt").write_text("")
    seed = str(base / "v015" / "seed.txt")
    assert [v.version.value for v in all_versions(seed)] == [15, 17]


def test_missing_versions(publish_tree):
    """Gaps between existing versions should be returned."""
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    # versions 15, 16, 17, 20 exist → gaps are 18, 19
    assert missing_versions(seed) == [18, 19]


def test_missing_versions_no_gaps(tmp_path):
    base = tmp_path / "publish"
    for n in (15, 16, 17):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text("")
    seed = str(base / "v015" / "model" / "char_geo_v015.abc")
    assert missing_versions(seed) == []


def test_missing_versions_empty(tmp_path):
    """No files on disk returns empty list."""
    # path doesn't match anything on disk
    result = missing_versions(str(tmp_path / "render_v001.exr"))
    assert result == []
