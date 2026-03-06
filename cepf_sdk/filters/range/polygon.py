# cepf_sdk/filters/range/polygon.py
"""多角形柱フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

# 多角形頂点 (XY 平面) のデフォルト。空リストの場合は全点を通過させる。
DEFAULT_POLYGON: List[Tuple[float, float]] = []
Z_MIN: float = -float("inf")  # Z 下限 [m]
Z_MAX: float =  float("inf")  # Z 上限 [m]
# NOTE: PolygonFilter の内外判定ループは Python で実装されているため
#       CuPy による GPU 演算は行わない。数万点程度なら CPU で十分高速。


@dataclass
class PolygonFilter(PointFilter):
    """
    XY平面の多角形内 × Z範囲の点群をフィルタリング。
    レイキャスティング法で内外判定。
    """
    polygon: List[Tuple[float, float]] = field(default_factory=list)
    z_min: float = -float('inf')
    z_max: float = float('inf')
    invert: bool = False
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        n = len(x)
        inside = np.zeros(n, dtype=bool)

        if len(self.polygon) >= 3:
            poly = np.asarray(self.polygon, dtype=np.float64)
            n_verts = len(poly)
            for i in range(n_verts):
                j = (i + 1) % n_verts
                xi, yi = poly[i]
                xj, yj = poly[j]

                cond = ((yi > y) != (yj > y)) & (
                    x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
                )
                inside ^= cond

        mask = inside & (z >= self.z_min) & (z <= self.z_max)

        if self.invert:
            mask = ~mask
        return mask
