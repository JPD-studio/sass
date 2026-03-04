# cepf_sdk/filters/statistical/sor.py
"""Statistical Outlier Removal (SOR)"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class StatisticalOutlierRemoval(PointFilter):
    """
    k近傍の平均距離が (全体平均 + std_ratio × 標準偏差) を超える点を除去。
    """
    k_neighbors: int = 10
    std_ratio: float = 1.0
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        from scipy.spatial import cKDTree

        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        pts = np.stack([x, y, z], axis=-1)
        valid = ~np.any(np.isnan(pts), axis=1)
        mask = np.zeros(len(x), dtype=bool)

        if np.count_nonzero(valid) <= self.k_neighbors:
            mask[valid] = True
            return mask

        tree = cKDTree(pts[valid])
        distances, _ = tree.query(pts[valid], k=self.k_neighbors + 1)
        # 最初の列は自分自身（距離0）なので除外
        mean_dists = np.mean(distances[:, 1:], axis=1)

        global_mean = np.mean(mean_dists)
        global_std = np.std(mean_dists)
        threshold = global_mean + self.std_ratio * global_std

        valid_indices = np.where(valid)[0]
        mask[valid_indices] = mean_dists <= threshold

        return mask
