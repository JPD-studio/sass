# cepf_sdk/filters/classification/noise.py
"""ノイズ検出フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.enums import PointFlag
from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class NoiseClassifier(PointFilter):
    """
    孤立点をノイズとして NOISE フラグを付与。
    点は削除しない（FLAG モード）。
    """
    neighbors: int = 5
    radius: float = 0.3
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
