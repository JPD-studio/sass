# cepf_sdk/filters/statistical/ror.py
"""Radius Outlier Removal (ROR)"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class RadiusOutlierRemoval(PointFilter):
    """
    半径内の近傍点数が閾値未満の孤立点を除去。
    scipy.spatial.cKDTree を使用。
    """
    radius_m: float = 0.3
    min_neighbors: int = 5
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        from scipy.spatial import cKDTree

        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        pts = np.stack([x, y, z], axis=-1)

        # NaN を含む点は除去
        valid = ~np.any(np.isnan(pts), axis=1)
        mask = np.zeros(len(x), dtype=bool)

        if np.count_nonzero(valid) == 0:
            return mask

        tree = cKDTree(pts[valid])
        counts = tree.query_ball_point(pts[valid], r=self.radius_m, return_length=True)
        counts_arr = np.asarray(counts)

        # 自分自身もカウントされるため min_neighbors + 1
        valid_indices = np.where(valid)[0]
        mask[valid_indices] = counts_arr >= (self.min_neighbors + 1)

        return mask
