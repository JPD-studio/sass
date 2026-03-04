# cepf_sdk/filters/classification/ground.py
"""地面検出フィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.enums import PointFlag
from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class GroundClassifier(PointFilter):
    """
    Z座標の閾値以下の点に GROUND フラグを付与。
    点は削除しない（FLAG モード）。
    """
    z_threshold: float = -0.3
    mode: FilterMode = FilterMode.FLAG
    flag_bit: int = PointFlag.GROUND

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """地面でない点 = True、地面の点 = False"""
        z = np.asarray(points["z"])
        return z > self.z_threshold
