# cepf_sdk/filters/range/spherical.py
"""球形フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

RADIUS_M: float = 10.0  # 球の半径 [m]
CX:       float =  0.0  # 中心 X [m]
CY:       float =  0.0  # 中心 Y [m]
CZ:       float =  0.0  # 中心 Z [m]


@dataclass
class SphericalFilter(PointFilter):
    """
    球形に点群をフィルタリング。
    中心 (cx, cy, cz) からの距離が radius_m 以内の点を残す。
    CuPy が利用可能な場合は GPU で演算する。
    """
    radius_m: float = field(default_factory=lambda: RADIUS_M)
    cx:       float = field(default_factory=lambda: CX)
    cy:       float = field(default_factory=lambda: CY)
    cz:       float = field(default_factory=lambda: CZ)
    invert:   bool  = False
    mode:     FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()
        x = xp.asarray(points["x"], dtype=xp.float32)
        y = xp.asarray(points["y"], dtype=xp.float32)
        z = xp.asarray(points["z"], dtype=xp.float32)

        dx = x - self.cx
        dy = y - self.cy
        dz = z - self.cz
        d2 = dx * dx + dy * dy + dz * dz

        mask = d2 <= self.radius_m * self.radius_m

        if self.invert:
            mask = ~mask
        return _to_numpy(mask)
