"""Decoder adapters for the OlmoEarth fine-tune.

Separate from ``pooling.py`` on purpose: that module is deliberately free of any rslearn/FM
import so its phenology-pooling proof runs on plain CPU torch in CI. This module *does* import
rslearn, so it only loads where rslearn is installed (the training venv), not in the unit-test path.
"""

from __future__ import annotations

from typing import Any

from rslearn.models.pooling_decoder import SegmentationPoolingDecoder
from rslearn.train.tasks.segmentation import FeatureMaps


class TemporalSegmentationPoolingDecoder(SegmentationPoolingDecoder):
    """``SegmentationPoolingDecoder`` that reads spatial dims from a **temporal** input.

    The stock decoder broadcasts its single pooled prediction to ``h, w`` taken from
    ``context.inputs[0][image_key].image.shape[1:3]``. That indexing assumes a 3-D ``[C, H, W]``
    image — the single-timestep case. Our phenology cube is 4-D, ``[bands, timesteps, H, W]``, so
    ``shape[1:3]`` returns ``(timesteps, H)`` and the model emits a ``(timesteps × H)`` prediction
    that cannot match a ``(H × W)`` target. The dry-run surfaced this as::

        RuntimeError: size mismatch (got input: [4, 4, 12, 2], target: [4, 2, 2])

    where the ``12`` is the monthly-mosaic count, not a spatial dimension.

    The fix is to take the spatial dims as the **last two axes**, which is correct for both the
    3-D and 4-D layouts. Nothing else about the mangrove-style pooling recipe changes: this is
    still one prediction per window broadcast to all pixels — appropriate for the small-window
    classification the scaffold mirrors, and the right thing to keep constant while the dry-run
    proves the pipeline end to end. Whether extent ultimately wants a *per-pixel* decoder
    (``UNetDecoder``) instead is a separate modelling decision, deliberately not made here.
    """

    def forward(self, intermediates: Any, context: Any) -> Any:
        """Broadcast the pooled vector to the input's true spatial extent (last two axes)."""
        # PoolingDecoder.forward -> per-window FeatureVector.
        output_probs = super(SegmentationPoolingDecoder, self).forward(intermediates, context)
        image = context.inputs[0][self.image_key].image
        h, w = image.shape[-2], image.shape[-1]
        feat_map = output_probs.feature_vector[:, :, None, None].repeat([1, 1, h, w])
        return FeatureMaps([feat_map])
