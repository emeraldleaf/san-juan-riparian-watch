"""CSU field-point crosswalk — the labels that make a beetle-aware Stage 2 possible.

Two things these tests exist to prevent, both of which have already happened once in this project:

1. **A silently incomplete crosswalk.** The NMRipMap fetch assumed every polygon was riparian and
   ~45% of the positive class turned out to be urban/agriculture/upland/water. An unmapped species
   string here must be a loud failure, never a guess.
2. **Defoliation collapsed into absence.** Defoliated tamarisk is still tamarisk — the same plant,
   browning early because a beetle ate it. Scoring it as absence is exactly what inverts the
   senescence discriminator the whole tamarisk literature depends on.

The `live` test hits the real 3,491-record file, because a crosswalk that covers a synthetic fixture
but not the actual vocabulary is worthless.
"""

from __future__ import annotations

import pytest

from riparian.labels.csu_points import (
    ABSENCE,
    AGRICULTURE,
    BEETLE_AFFECTED,
    CSU_POINTS_CSV_URL,
    DEAD,
    DEFOLIATED,
    LABEL_YEAR,
    LIVE,
    MIXED,
    NATIVE_RIPARIAN_WOODY,
    RUSSIAN_OLIVE,
    TAMARISK,
    LabeledPoint,
    beetle_affected,
    fix_coordinates,
    load_crosswalk,
    load_points,
    negatives,
)

CROSSWALK = load_crosswalk()


def _pt(label: str, condition: str | None = None) -> LabeledPoint:
    return LabeledPoint(
        lon=-108.0, lat=37.0, label=label, condition=condition, confidence=0.9,
        source_species="x", trip="t", plot_id="1",
    )


class TestCoordinateTransposition:
    """The `Virgin_River` trip carries lat in `x` and lon in `y` — all 119 rows."""

    def test_correct_orientation_is_left_alone(self) -> None:
        assert fix_coordinates(-108.5, 37.2) == (-108.5, 37.2)

    def test_transposed_pair_is_swapped(self) -> None:
        # As it appears in the source: x=36.9 (a latitude), y=-113.5 (a longitude)
        assert fix_coordinates(36.9, -113.5) == (-113.5, 36.9)

    def test_detection_is_by_RANGE_not_by_trip_name(self) -> None:
        """A new trip with the same defect must be caught, not trusted because it is not named."""
        lon, lat = fix_coordinates(38.0, -114.0)  # no trip name involved anywhere
        assert lon < 0 < lat

    def test_an_unusable_pair_fails_loudly(self) -> None:
        """Better to raise than to silently drop a field plot into the ocean."""
        with pytest.raises(ValueError, match="continental US"):
            fix_coordinates(10.0, 10.0)


class TestDefoliationIsAState:
    """The whole point of this dataset."""

    def test_red_tam_is_TAMARISK_with_a_defoliated_condition_not_an_absence(self) -> None:
        label, condition, _ = CROSSWALK["red tam"]
        assert label == TAMARISK, "beetle-defoliated tamarisk is still tamarisk"
        assert condition == DEFOLIATED

    def test_dead_tamarisk_is_still_tamarisk(self) -> None:
        label, condition, _ = CROSSWALK["dead tam"]
        assert label == TAMARISK
        assert condition == DEAD

    def test_live_dead_mix_is_tamarisk_mixed(self) -> None:
        label, condition, _ = CROSSWALK["live dead tam mix"]
        assert label == TAMARISK
        assert condition == MIXED

    @pytest.mark.parametrize("condition", [DEFOLIATED, MIXED, DEAD])
    def test_beetle_conditions_are_flagged(self, condition: str) -> None:
        assert _pt(TAMARISK, condition).is_beetle_affected
        assert condition in BEETLE_AFFECTED

    def test_live_tamarisk_is_not_beetle_affected(self) -> None:
        assert not _pt(TAMARISK, LIVE).is_beetle_affected

    def test_no_tamarisk_condition_is_ever_mapped_to_absence(self) -> None:
        """The error that would invert the senescence signal. Guard it explicitly."""
        for key, (label, _cond, _c) in CROSSWALK.items():
            if "tam" in key:
                assert label != ABSENCE, f"{key!r} must never be an absence"


class TestSpeciesSplit:
    """NMRipMap's `IC` conflates tamarisk with Russian olive. This must not."""

    def test_russian_olive_is_its_own_class(self) -> None:
        assert CROSSWALK["russian olive"][0] == RUSSIAN_OLIVE
        assert CROSSWALK["russian olive"][0] != TAMARISK

    def test_casing_variants_collapse_to_the_same_class(self) -> None:
        # `Russian olive` and `Russian Olive` are BOTH present in the source file.
        assert CROSSWALK["russian olive"][0] == CROSSWALK["russian olive"][0]
        assert "russian olive" in CROSSWALK
        assert CROSSWALK["tamarisk"][0] == TAMARISK

    def test_natives_are_distinguished_from_invasives(self) -> None:
        for native in ("cottonwood", "willow", "box elder"):
            assert CROSSWALK[native][0] == NATIVE_RIPARIAN_WOODY
        assert not _pt(NATIVE_RIPARIAN_WOODY).is_invasive
        assert _pt(TAMARISK, LIVE).is_invasive
        assert _pt(RUSSIAN_OLIVE).is_invasive


class TestNegatives:
    def test_real_absences_replace_random_background(self) -> None:
        pts = [_pt(ABSENCE), _pt(AGRICULTURE), _pt(TAMARISK, LIVE), _pt(NATIVE_RIPARIAN_WOODY)]
        neg = negatives(pts)
        assert {p.label for p in neg} == {ABSENCE, AGRICULTURE}
        assert all(not p.is_invasive for p in neg)

    def test_agriculture_is_a_negative(self) -> None:
        """Agriculture is the class the weak labels notoriously failed on (~0.00 F1 on the Animas)."""
        assert CROSSWALK["ag"][0] == AGRICULTURE


class TestVintage:
    def test_label_year_is_2017(self) -> None:
        """Fit against 2017 imagery. Fitting these labels to another year is self-inflicted noise."""
        assert LABEL_YEAR == 2017


class TestEcoregionMatchedPool:
    """The lower basin is excluded on principle, not on convenience."""

    def test_arizona_and_virgin_river_are_excluded(self) -> None:
        from riparian.labels.csu_points import COLORADO_PLATEAU_TRIPS, LOWER_BASIN_TRIPS
        assert COLORADO_PLATEAU_TRIPS.isdisjoint(LOWER_BASIN_TRIPS)
        assert "Arizona" in LOWER_BASIN_TRIPS
        assert "Escalante" in COLORADO_PLATEAU_TRIPS

    def test_pool_keeps_only_plateau_trips(self) -> None:
        from riparian.labels.csu_points import colorado_plateau
        pts = [
            LabeledPoint(-111.0, 38.0, TAMARISK, DEFOLIATED, 0.9, "red tam", "Escalante", "1"),
            LabeledPoint(-112.0, 33.0, TAMARISK, LIVE, 0.9, "tamarisk", "Arizona", "2"),
        ]
        pool = colorado_plateau(pts)
        assert [p.trip for p in pool] == ["Escalante"], (
            "Arizona is a different desert at a different stage of biocontrol (87% still live in "
            "2017) — pooling it imports the domain shift the model must not learn"
        )


@pytest.mark.live
class TestAgainstTheRealFile:
    """A crosswalk that covers a fixture but not the real vocabulary is worthless."""

    def test_every_species_string_in_the_source_is_mapped(self) -> None:
        import csv as _csv

        import requests

        resp = requests.get(CSU_POINTS_CSV_URL, timeout=120)
        resp.raise_for_status()
        rows = list(_csv.DictReader(resp.text.splitlines()))

        seen = {" ".join((r["Species"] or "").strip().lower().split()) for r in rows}
        seen.discard("")
        unmapped = seen - set(CROSSWALK)
        assert not unmapped, f"add these to csu_points_crosswalk.csv: {sorted(unmapped)}"

    def test_the_beetle_labels_are_actually_there(self) -> None:
        pts = load_points(CSU_POINTS_CSV_URL)
        assert len(pts) > 3_400
        beetle = beetle_affected(pts)
        assert len(beetle) > 500, "547 expected — the labels our defoliation claim depends on"

    def test_no_point_lands_in_the_wrong_hemisphere(self) -> None:
        """The Virgin_River transposition, caught end-to-end."""
        for p in load_points(CSU_POINTS_CSV_URL):
            assert -125.0 <= p.lon <= -100.0, f"{p.trip}: lon {p.lon} is not in the western US"
            assert 25.0 <= p.lat <= 45.0
