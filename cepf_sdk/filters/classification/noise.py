# cepf_sdk/filters/classification/noise.py
"""ノイズ検出フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.enums import PointFlag
from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

NEIGHBORS: int   = 5    # 近傍点数の閾値 (この数未満でノイズ判定)
RADIUS:    float = 0.3  # 近傍探索半径 [m]
# NOTE: scipy.cKDTree は CPU 専用のため CuPy による GPU 演算は行わない。


@dataclass
class NoiseClassifier(PointFilter):
    """
    孤立点をノイズとして NOISE フラグを付与。
    点は削除しない（FLAG モード）。
    scipy.cKDTree を使用するため CPU 演算のみ。
    """
    neighbors: int   = field(default_factory=lambda: NEIGHBORS)
    radius:    float = field(default_factory=lambda: RADIUS)
    mode: FilterMode = FilterMode.FLAG
    flag_bit: int = PointFlag.NOISE

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """ノイズでない点 = True、ノイズの点 = False"""
        from scipy.spatial import cKDTree

        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        n = len(x)
        pts = np.stack([x, y, z], axis=-1)
        valid = ~np.any(np.isnan(pts), axis=1)

        # デフォルトはノイズではない
        mask = np.ones(n, dtype=bool)

        if np.count_nonzero(valid) == 0:
            return mask

        tree = cKDTree(pts[valid])
        counts = tree.query_ball_point(pts[valid], r=self.radius, return_length=True)
        counts_arr = np.asarray(counts)

        valid_indices = np.where(valid)[0]
        # 近傍点数が足りない点はノイズ（mask = False）
        mask[valid_indices] = counts_arr >= (self.neighbors + 1)

        return mask
