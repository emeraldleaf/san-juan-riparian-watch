"""Unit tests for invasive-label + weak-label logic."""

from riparian.health.invasive import is_invasive


def test_is_invasive_tamarisk():
    assert is_invasive(
        "Lowland Native-Introduced Tamarisk Deciduous Riparian Forest", None,
    )


def test_is_invasive_russian_olive():
    assert is_invasive(
        "Russian Olive-Tamarisk Introduced Riparian Woodland and Scrub", None,
    )


def test_is_invasive_ruderal_from_nvc():
    assert is_invasive(None, "Interior West Ruderal Riparian Forest & Scrub")


def test_is_invasive_introduced_keyword():
    assert is_invasive("Some Introduced Riparian Vegetation", None)


def test_is_invasive_native_is_false():
    assert not is_invasive(
        "Rocky Mountain Cottonwood-Willow Riparian Forest", "Native Riparian",
    )


def test_is_invasive_handles_none():
    assert not is_invasive(None, None)


def test_is_invasive_case_insensitive():
    assert is_invasive("lowland TAMARISK scrub", None)
