# cepf_sdk/filters/range/cylindrical.py
"""円筒形フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class CylindricalFilter(PointFilter):
    """
    円筒形に点群をフィルタリング。
    中心 (cx, cy) からの水平距離が radius_m 以内、
    かつ z が z_min_m 以上 z_max_m 以下の点を残す。
    """
    radius_m: float = 10.0
    z_min_m: float = 0.0
    z_max_m: float = 30.0
    cx: float = 0.0
    cy: float = 0.0
    invert: bool = False
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        dx = x - self.cx
        dy = y - self.cy
        r2 = dx * dx + dy * dy

        mask = (r2 <= self.radius_m * self.radius_m) & (z >= self.z_min_m) & (z <= self.z_max_m)

        if self.invert:
            mask = ~mask
        return mask
