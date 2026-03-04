# cepf_sdk/filters/attribute/confidence.py
"""信頼度フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class ConfidenceFilter(PointFilter):
    """信頼度の閾値フィルタ"""
    min_confidence: float = 0.5
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        confidence = np.asarray(points.get("confidence", np.ones(0, dtype=np.float32)))
        return confidence >= self.min_confidence
