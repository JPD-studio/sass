# cepf_sdk/filters/range/box.py
"""直方体フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class BoxFilter(PointFilter):
    """
    直方体（AABB）で点群をフィルタリング。
    """
    x_min: float = -10.0
    x_max: float = 10.0
    y_min: float = -10.0
    y_max: float = 10.0
    z_min: float = -10.0
    z_max: float = 10.0
    invert: bool = False
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        mask = (
            (x >= self.x_min) & (x <= self.x_max) &
            (y >= self.y_min) & (y <= self.y_max) &
            (z >= self.z_min) & (z <= self.z_max)
        )

        if self.invert:
            mask = ~mask
        return mask
