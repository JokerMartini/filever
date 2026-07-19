import pytest

from filever import discover
from filever.tokens import PlaceholderNotation


@pytest.mark.parametrize(
    "path, expected_versions, expected_agrees",
    [
        ("/projects/v2/assets/character_v003.png", [(2, 1, "v"), (3, 3, "v")], False),
        ("/renders/2024/shot_010/comp_v012.exr", [(12, 3, "v")], True),
        ("/lib/python3.11/site-packages/tool_v1.py", [(1, 1, "v")], True),
        ("/sequences/sq050/sh0100/render_%03d.jpg", [], True),
        ("/build/release-1.4.2/binary_1.4.2.exe", [], True),
        ("/cache/v5/textures/wood_v2_diffuse.tga", [(5, 1, "v"), (2, 1, "v")], False),
        ("/frames/scene01/frame_####.png", [], True),
        ("/v10/output/final_v10.mov", [(10, 2, "v"), (10, 2, "v")], True),
        ("/app/2.0/config/settings_v1.json", [(1, 1, "v")], True),
        ("/shots/sh020/plate_v001.####.dpx", [(1, 3, "v")], True),
        ("/data/version_3/dataset_v3.csv", [(3, 1, "v")], True),
        ("/mnt/v001/comp/beauty_1001.exr", [(1, 3, "v")], True),
        ("/publish/v015/model/char_geo_v012.abc", [(15, 3, "v"), (12, 3, "v")], False),
        ("/tools/blender-4.1/addon_%04d.py", [], True),
        ("/anim/sq010_sh0050/anim_v7.blend", [(7, 1, "v")], True),
        ("/releases/v2.1.0/notes_v2.txt", [(2, 1, "v"), (2, 1, "v")], True),
        ("/assets/prop_v009/lod_v2.fbx", [(9, 3, "v"), (2, 1, "v")], False),
        ("/publish/v015/model/char_geo_v015.abc", [(15, 3, "v"), (15, 3, "v")], True),
        (
            "/publish/char_geo_v015/model/char_geo_v015.abc",
            [(15, 3, "v"), (15, 3, "v")],
            True,
        ),
        ("char_v001_v002.png", [(2, 3, "v")], True),
        ("V002/render.exr", [(2, 3, "V")], True),
    ],
)
def test_discover_fixtures(path, expected_versions, expected_agrees):
    pv = discover(path)
    actual = [(v.value, v.pad, v.case) for v in pv.versions]
    assert actual == expected_versions, f"versions mismatch for {path!r}"
    assert pv.agrees() is expected_agrees, f"agrees mismatch for {path!r}"


def test_boundary_rules():
    assert discover("versionv001.png").versions == ()
    assert discover("v001a.png").versions == ()
    assert discover("MOV3D_render.exr").versions == ()
    assert discover("char_v001.png").versions[0].value == 1
    assert discover("v001").versions[0].value == 1
    assert discover("v001.png").versions[0].value == 1


def test_case_insensitive_match_case_preserved():
    pv_lower = discover("char_v001.png")
    pv_upper = discover("char_V001.png")
    assert pv_lower.versions[0].case == "v"
    assert pv_upper.versions[0].case == "V"


def test_rightmost_wins_tiebreaker():
    pv = discover("char_v001_v002.png")
    assert len(pv.versions) == 1
    assert pv.versions[0].value == 2


def test_leftmost_tiebreaker_opt_in():
    pv = discover("char_v001_v002.png", tiebreaker="leftmost")
    assert pv.versions[0].value == 1


def test_pad_disagreement():
    pv = discover("/publish/v01/model/char_geo_v1.abc")
    assert pv.agrees() is False


def test_placeholders():
    pv = discover("/shots/sh020/plate_v001.####.dpx")
    assert len(pv.placeholders) == 1
    assert pv.placeholders[0].notation == PlaceholderNotation.HASH
    assert pv.placeholders[0].width == 4

    pv2 = discover("/sequences/sq050/sh0100/render_%03d.jpg")
    assert len(pv2.placeholders) == 1
    assert pv2.placeholders[0].notation == PlaceholderNotation.PRINTF
    assert pv2.placeholders[0].width == 3


def test_folder_and_filename_accessors():
    pv = discover("/publish/v015/model/char_geo_v012.abc")
    assert pv.filename_version is not None
    assert pv.filename_version.value == 12
    assert len(pv.folder_versions) == 1
    assert pv.folder_versions[0].value == 15


def test_windows_path():
    pv = discover(r"C:\publish\v015\char.abc")
    assert pv.versions[0].value == 15
    assert pv.versions[0].pad == 3
