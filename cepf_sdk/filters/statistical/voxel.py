# cepf_sdk/filters/statistical/voxel.py
"""ボクセルダウンサンプリング"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

VOXEL_SIZE: float = 0.05  # ボクセルグリッドサイズ [m]


@dataclass
class VoxelDownsample(PointFilter):
    """
    ボクセルグリッド内の最初の点だけ残す。
    CuPy が利用可能な場合は GPU で演算する。
    """
    voxel_size: float = field(default_factory=lambda: VOXEL_SIZE)
    mode:     FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()

        x = xp.asarray(points["x"], dtype=xp.float32)
        y = xp.asarray(points["y"], dtype=xp.float32)
        z = xp.asarray(points["z"], dtype=xp.float32)

        n = len(x)
        if n == 0:
            return np.zeros(0, dtype=bool)

        inv = xp.float32(1.0 / self.voxel_size)
        ix = xp.floor(x * inv).astype(xp.int64)
        iy = xp.floor(y * inv).astype(xp.int64)
        iz = xp.floor(z * inv).astype(xp.int64)

        # 簡易ハッシュでユニークなボクセルを見つける
        keys = ix * xp.int64(1_000_003) + iy * xp.int64(1_000_033) + iz
        _, first_indices = xp.unique(keys, return_index=True)

        # first_indices を numpy に戻して mask を作成
        fi = _to_numpy(first_indices)
        mask = np.zeros(n, dtype=bool)
        mask[fi] = True
        return mask
