# cepf_sdk/filters/attribute/intensity.py
"""強度フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

MIN_INTENSITY: float = 0.0  # 強度下限 (0.0〜1.0 の正規化値)
MAX_INTENSITY: float = 1.0  # 強度上限 (0.0〜1.0 の正規化値)


@dataclass
class IntensityFilter(PointFilter):
    """強度の閾値フィルタ。CuPy が利用可能な場合は GPU で演算する。"""
    min_intensity: float = field(default_factory=lambda: MIN_INTENSITY)
    max_intensity: float = field(default_factory=lambda: MAX_INTENSITY)
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()
        intensity = xp.asarray(
            points.get("intensity", np.zeros(0, dtype=np.float32)),
            dtype=xp.float32,
        )
        mask = (intensity >= self.min_intensity) & (intensity <= self.max_intensity)
        return _to_numpy(mask)
