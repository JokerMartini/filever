import os

import pytest

from filever import (
    AmbiguousVersion,
    NoVersionFound,
    UnresolvedPlaceholder,
)
from filever.disk import (
    earliest_on_disk,
    latest_on_disk,
    list_on_disk,
    next_version,
    previous_version,
)


@pytest.fixture
def publish_tree(tmp_path):
    base = tmp_path / "publish"
    for n in (15, 16, 17, 20):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text(f"content-{n}")
    return base


def test_list_on_disk_matching_group(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    result = list_on_disk(seed)
    assert result == [15, 16, 17, 20]


def test_latest_and_earliest(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert latest_on_disk(seed) == 20
    assert earliest_on_disk(seed) == 15


def test_next_version_on_disk(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert next_version(seed) == 16
    seed17 = str(publish_tree / "v017" / "model" / "char_geo_v017.abc")
    assert next_version(seed17) == 20


def test_previous_version_on_disk(publish_tree):
    seed = str(publish_tree / "v017" / "model" / "char_geo_v017.abc")
    assert previous_version(seed) == 16


def test_next_version_no_higher(publish_tree):
    seed = str(publish_tree / "v020" / "model" / "char_geo_v020.abc")
    assert next_version(seed) is None


def test_previous_version_no_lower(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert previous_version(seed) is None


def test_next_version_exists_false(publish_tree):
    seed = str(publish_tree / "v015" / "model" / "char_geo_v015.abc")
    assert next_version(seed, exists=False) == 16
    assert next_version(seed, exists=False, driver="folder") == 16


def test_previous_version_exists_false():
    assert previous_version("char_v005.png", exists=False) == 4
    assert previous_version("char_v000.png", exists=False) is None


def test_next_version_exists_false_by_n_style():
    assert next_version("char_v005.png", exists=False) == 6


def test_list_skips_orphaned_folder(tmp_path):
    """A folder v020 without the expected file should not appear in the list."""
    base = tmp_path / "publish"
    for n in (15, 16):
        d = base / f"v{n:03d}" / "model"
        d.mkdir(parents=True)
        (d / f"char_geo_v{n:03d}.abc").write_text("")
    orphan = base / "v020" / "model"
    orphan.mkdir(parents=True)  # no file inside
    seed = str(base / "v015" / "model" / "char_geo_v015.abc")
    assert list_on_disk(seed) == [15, 16]


def test_no_versions_raises(tmp_path):
    (tmp_path / "no_version.txt").write_text("")
    with pytest.raises(NoVersionFound):
        list_on_disk(str(tmp_path / "no_version.txt"))


def test_placeholder_raises(tmp_path):
    with pytest.raises(UnresolvedPlaceholder):
        list_on_disk(str(tmp_path / "render_%03d.jpg"))


def test_ambiguous_mismatch_raises(tmp_path):
    base = tmp_path / "cache"
    (base / "v5" / "textures").mkdir(parents=True)
    (base / "v5" / "textures" / "wood_v2_diffuse.tga").write_text("")
    seed = str(base / "v5" / "textures" / "wood_v2_diffuse.tga")
    with pytest.raises(AmbiguousVersion):
        list_on_disk(seed)


def test_mismatch_with_driver(tmp_path):
    base = tmp_path / "cache"
    for n in (5, 6, 7):
        d = base / f"v{n}" / "textures"
        d.mkdir(parents=True)
        (d / "wood_v2_diffuse.tga").write_text("")
    seed = str(base / "v5" / "textures" / "wood_v2_diffuse.tga")
    assert list_on_disk(seed, driver="folder") == [5, 6, 7]


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
    assert list_on_disk(seed) == [15, 16]
    assert list_on_disk(seed, include_symlinks=True) == [15, 16]


def test_case_strict_scan(tmp_path):
    base = tmp_path
    (base / "v015").mkdir()
    (base / "v015" / "char_V015.abc").write_text("")
    (base / "v016").mkdir()
    (base / "v016" / "char_V016.abc").write_text("")
    seed = str(base / "v015" / "char_V015.abc")
    assert list_on_disk(seed) == [15, 16]


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
    result = list_on_disk(seed)
    assert result == [15, 17]
