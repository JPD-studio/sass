# cepf_sdk/filters/classification/ground.py
"""地面検出フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.enums import PointFlag
from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

Z_THRESHOLD: float = -0.3  # 地面と判定する Z 閾値 [m] (この値以下を GROUND 扱い)


@dataclass
class GroundClassifier(PointFilter):
    """
    Z座標の閾値以下の点に GROUND フラグを付与。
    点は削除しない（FLAG モード）。
    CuPy が利用可能な場合は GPU で演算する。
    """
    z_threshold: float = field(default_factory=lambda: Z_THRESHOLD)
    mode: FilterMode = FilterMode.FLAG
    flag_bit: int = PointFlag.GROUND

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """地面でない点 = True、地面の点 = False"""
        xp = _get_xp()
        z = xp.asarray(points["z"], dtype=xp.float32)
        mask = z > self.z_threshold
        return _to_numpy(mask)
