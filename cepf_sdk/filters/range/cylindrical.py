# cepf_sdk/filters/range/cylindrical.py
"""円筒形フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

RADIUS_M: float = 10.0   # 水平半径 [m]
Z_MIN_M:  float = -30.0  # Z 下限 [m]
Z_MAX_M:  float =  30.0  # Z 上限 [m]
CX:       float =   0.0  # 中心 X [m]
CY:       float =   0.0  # 中心 Y [m]


@dataclass
class CylindricalFilter(PointFilter):
    """
    円筒形に点群をフィルタリング。
    中心 (cx, cy) からの水平距離が radius_m 以内、
    かつ z が z_min_m 以上 z_max_m 以下の点を残す。
    CuPy が利用可能な場合は GPU で演算する。
    """
    radius_m: float = field(default_factory=lambda: RADIUS_M)
    z_min_m:  float = field(default_factory=lambda: Z_MIN_M)
    z_max_m:  float = field(default_factory=lambda: Z_MAX_M)
    cx:       float = field(default_factory=lambda: CX)
    cy:       float = field(default_factory=lambda: CY)
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
        r2 = dx * dx + dy * dy

        mask = (r2 <= self.radius_m * self.radius_m) & (z >= self.z_min_m) & (z <= self.z_max_m)

        if self.invert:
            mask = ~mask
        return _to_numpy(mask)
