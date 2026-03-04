# cepf_sdk/filters/statistical/voxel.py
"""ボクセルダウンサンプリング"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class VoxelDownsample(PointFilter):
    """
    ボクセルグリッド内の最初の点だけ残す。
    """
    voxel_size: float = 0.05
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        n = len(x)
        if n == 0:
            return np.zeros(0, dtype=bool)

        inv = 1.0 / self.voxel_size
        ix = np.floor(x * inv).astype(np.int64)
        iy = np.floor(y * inv).astype(np.int64)
        iz = np.floor(z * inv).astype(np.int64)

        # ユニークなボクセルを見つける
        keys = ix * 1000003 + iy * 1000033 + iz  # 簡易ハッシュ
        _, first_indices = np.unique(keys, return_index=True)

        mask = np.zeros(n, dtype=bool)
        mask[first_indices] = True
        return mask
