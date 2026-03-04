# cepf_sdk/filters/range/spherical.py
"""球形フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class SphericalFilter(PointFilter):
    """
    球形に点群をフィルタリング。
    中心 (cx, cy, cz) からの距離が radius_m 以内の点を残す。
    """
    radius_m: float = 10.0
    cx: float = 0.0
    cy: float = 0.0
    cz: float = 0.0
    invert: bool = False
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        dx = x - self.cx
        dy = y - self.cy
        dz = z - self.cz
        d2 = dx * dx + dy * dy + dz * dz

        mask = d2 <= self.radius_m * self.radius_m

        if self.invert:
            mask = ~mask
        return mask
