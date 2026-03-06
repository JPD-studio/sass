# cepf_sdk/filters/range/box.py
"""直方体フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

X_MIN: float = -10.0  # X 下限 [m]
X_MAX: float =  10.0  # X 上限 [m]
Y_MIN: float = -10.0  # Y 下限 [m]
Y_MAX: float =  10.0  # Y 上限 [m]
Z_MIN: float = -10.0  # Z 下限 [m]
Z_MAX: float =  10.0  # Z 上限 [m]


@dataclass
class BoxFilter(PointFilter):
    """
    直方体（AABB）で点群をフィルタリング。
    CuPy が利用可能な場合は GPU で演算する。
    """
    x_min: float = field(default_factory=lambda: X_MIN)
    x_max: float = field(default_factory=lambda: X_MAX)
    y_min: float = field(default_factory=lambda: Y_MIN)
    y_max: float = field(default_factory=lambda: Y_MAX)
    z_min: float = field(default_factory=lambda: Z_MIN)
    z_max: float = field(default_factory=lambda: Z_MAX)
    invert:   bool  = False
    mode:     FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()
        x = xp.asarray(points["x"], dtype=xp.float32)
        y = xp.asarray(points["y"], dtype=xp.float32)
        z = xp.asarray(points["z"], dtype=xp.float32)

        mask = (
            (x >= self.x_min) & (x <= self.x_max) &
            (y >= self.y_min) & (y <= self.y_max) &
            (z >= self.z_min) & (z <= self.z_max)
        )

        if self.invert:
            mask = ~mask
        return _to_numpy(mask)
