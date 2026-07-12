"""CO-RIP labels — vintage and confidence, both of which are load-bearing.

Two failures these pin, both of which this project has already committed once:

1. **Fitting labels against the wrong year.** NMRipMap is NAIP-2020-derived and we fitted it against
   2024 imagery, injecting label noise we made ourselves. CO-RIP models **2006 and 2016**; anything
   else must raise.
2. **Treating a weak label as ground truth.** CO-RIP's OOB error spans **2–35% by ecoregion**, and the
   authors state it *"may likely over predict riparian vegetation in high elevation environments"*.
   Turkey Creek — the tile we want CO-RIP for — is Southern Rockies: **northern, mountainous, high
   elevation.** The confidence must be lowest exactly there, or the label set teaches the model that
   upland IS riparian, which is the same failure the NMRipMap crosswalk exists to prevent.
"""

from __future__ import annotations

import pytest

from riparian.labels.corip import (
    ABSENCE,
    DEFAULT_CONFIDENCE,
    ECOREGION_CONFIDENCE,
    HIGH_ELEVATION_ECOREGIONS,
    LABEL_YEARS,
    PRESENCE,
    RESOLUTION_M,
    confidence_for,
    download_instructions,
    label_from_pixel,
)


class TestVintage:
    def test_corip_models_2006_and_2016(self) -> None:
        """From the source team's own report — the Dryad page never says."""
        assert LABEL_YEARS == (2006, 2016)

    def test_resolution_is_landsat_30m(self) -> None:
        assert RESOLUTION_M == 30

    @pytest.mark.parametrize("year", [2006, 2016])
    def test_a_modelled_year_is_accepted(self, year: int) -> None:
        assert label_from_pixel(PRESENCE, year, "colorado_plateau") is not None

    @pytest.mark.parametrize("year", [2020, 2024, 2017])
    def test_an_unmodelled_year_RAISES(self, year: int) -> None:
        """The NMRipMap mistake, made impossible rather than merely discouraged."""
        with pytest.raises(ValueError, match="fit against the label's year"):
            label_from_pixel(PRESENCE, year, "colorado_plateau")


class TestConfidenceIsLowestWhereWeNeedItMost:
    """The uncomfortable fact: CO-RIP is worst exactly on the tile we want it for."""

    def test_turkey_creek_ecoregion_has_the_lowest_confidence(self) -> None:
        southern_rockies = ECOREGION_CONFIDENCE["southern_rockies"]
        arid = ECOREGION_CONFIDENCE["sonoran_basin"]
        assert southern_rockies < arid, (
            "CO-RIP's OOB error is 2-35% BY ECOREGION; north/mountainous is the bad end"
        )
        assert southern_rockies <= 0.6

    def test_high_elevation_ecoregions_are_flagged_for_over_prediction(self) -> None:
        """The authors: 'our map may likely over predict riparian vegetation at high elevation'."""
        label = label_from_pixel(PRESENCE, 2016, "southern_rockies")
        assert label is not None
        assert label.over_prediction_risk, "Turkey Creek must be flagged, not silently trusted"
        assert "southern_rockies" in HIGH_ELEVATION_ECOREGIONS

    def test_arid_lowland_is_not_flagged(self) -> None:
        label = label_from_pixel(PRESENCE, 2016, "sonoran_basin")
        assert label is not None
        assert not label.over_prediction_risk

    def test_unknown_ecoregion_gets_a_CONSERVATIVE_default(self) -> None:
        """An unknown region must not inherit an optimistic number."""
        conf = confidence_for("some_unmapped_region")
        assert conf == DEFAULT_CONFIDENCE
        assert conf < ECOREGION_CONFIDENCE["colorado_plateau"]

    def test_ecoregion_key_normalization(self) -> None:
        assert confidence_for("Southern Rockies") == ECOREGION_CONFIDENCE["southern_rockies"]
        assert confidence_for("southern-rockies") == ECOREGION_CONFIDENCE["southern_rockies"]


class TestPixelMapping:
    def test_presence_and_absence(self) -> None:
        assert label_from_pixel(PRESENCE, 2016, "colorado_plateau").is_riparian is True
        assert label_from_pixel(ABSENCE, 2016, "colorado_plateau").is_riparian is False

    def test_an_unexpected_value_is_dropped_not_guessed(self) -> None:
        """CO-RIP's raster is binary. Anything else is nodata — guessing is how labels go 45% wrong."""
        assert label_from_pixel(255, 2016, "colorado_plateau") is None
        assert label_from_pixel(1, 2016, "colorado_plateau") is None

    def test_labels_carry_their_provenance(self) -> None:
        label = label_from_pixel(PRESENCE, 2016, "southern_rockies")
        assert label.source == "corip"
        assert label.year == 2016
        assert 0.0 < label.confidence <= 1.0


class TestDownloadInstructions:
    def test_they_name_the_year_and_the_over_prediction_risk(self) -> None:
        """Dryad blocks automated fetches; a 403 is a far worse failure than clear instructions."""
        text = download_instructions()
        assert "2006" in text and "2016" in text
        assert "OVER-PREDICT" in text.upper()
        assert "ground truth" in text
