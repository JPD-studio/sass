# cepf_sdk/filters/attribute/intensity.py
"""強度フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class IntensityFilter(PointFilter):
    """強度の閾値フィルタ"""
    min_intensity: float = 0.0
    max_intensity: float = 1.0
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        intensity = np.asarray(points.get("intensity", np.zeros(0, dtype=np.float32)))
        return (intensity >= self.min_intensity) & (intensity <= self.max_intensity)
