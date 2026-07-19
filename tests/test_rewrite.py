import pytest

from filever import (
    AmbiguousVersion,
    NoDriverToken,
    bump,
    discover,
    rewrite_token,
    set_version,
)


def test_bump_preserves_pad():
    assert bump("char_v001.png") == "char_v002.png"
    assert bump("char_v009.png") == "char_v010.png"
    assert bump("char_v9.png") == "char_v10.png"


def test_bump_preserves_case():
    assert bump("char_V002.png") == "char_V003.png"


def test_bump_by_n():
    assert bump("char_v005.png", by=3) == "char_v008.png"
    assert bump("char_v005.png", by=-2) == "char_v003.png"


def test_bump_grouped_when_matching():
    assert bump("/publish/v015/model/char_geo_v015.abc") == "/publish/v016/model/char_geo_v016.abc"


def test_bump_by_2_grouped():
    assert (
        bump("/publish/v015/model/char_geo_v015.abc", by=2)
        == "/publish/v017/model/char_geo_v017.abc"
    )


def test_bump_v210_only_matched_span():
    assert bump("/releases/v2.1.0/notes_v2.txt") == "/releases/v3.1.0/notes_v3.txt"


def test_bump_raises_ambiguous_on_mismatch():
    with pytest.raises(AmbiguousVersion):
        bump("/cache/v5/textures/wood_v2_diffuse.tga")


def test_bump_with_driver_folder():
    result = bump("/cache/v5/textures/wood_v2_diffuse.tga", driver="folder")
    assert result == "/cache/v6/textures/wood_v2_diffuse.tga"


def test_bump_with_driver_filename():
    result = bump("/cache/v5/textures/wood_v2_diffuse.tga", driver="filename")
    assert result == "/cache/v5/textures/wood_v3_diffuse.tga"


def test_bump_raises_no_driver_token_when_class_missing():
    with pytest.raises(NoDriverToken):
        bump("/renders/2024/shot_010/comp_v012.exr", driver="folder")


def test_bump_pad_mismatch_is_ambiguous():
    with pytest.raises(AmbiguousVersion):
        bump("/publish/v01/model/char_geo_v1.abc")


def test_pad_mismatch_with_driver():
    result = bump("/publish/v01/model/char_geo_v1.abc", driver="folder")
    assert result == "/publish/v02/model/char_geo_v1.abc"


def test_set_version():
    assert set_version("char_v001.png", 42) == "char_v042.png"


def test_set_version_grouped():
    assert (
        set_version("/publish/v015/model/char_geo_v015.abc", 20)
        == "/publish/v020/model/char_geo_v020.abc"
    )


def test_rewrite_token():
    pv = discover("/publish/v015/model/char_geo_v015.abc")
    token = pv.filename_version
    assert token is not None
    result = rewrite_token(pv, token, 99)
    assert result == "/publish/v015/model/char_geo_v099.abc"


def test_bump_windows_path_preserves_separators():
    result = bump(r"C:\publish\v015\char.abc")
    assert result == r"C:\publish\v016\char.abc"


def test_driver_by_token_reference():
    pv = discover("/cache/v5/textures/wood_v2_diffuse.tga")
    folder_token = pv.folder_versions[0]
    result = bump(pv, driver=folder_token)
    assert result == "/cache/v6/textures/wood_v2_diffuse.tga"


def test_driver_ignored_on_matching_path():
    result = bump("/publish/v015/model/char_geo_v015.abc", driver="folder")
    assert result == "/publish/v016/model/char_geo_v016.abc"
