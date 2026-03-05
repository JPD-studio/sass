# cepf_sdk/filters/attribute/confidence.py
"""信頼度フィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

MIN_CONFIDENCE: float = 0.5  # 信頼度下限 (0.0〜1.0)


@dataclass
class ConfidenceFilter(PointFilter):
    """信頼度の閾値フィルタ。CuPy が利用可能な場合は GPU で演算する。"""
    min_confidence: float = field(default_factory=lambda: MIN_CONFIDENCE)
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()
        confidence = xp.asarray(
            points.get("confidence", np.ones(0, dtype=np.float32)),
            dtype=xp.float32,
        )
        mask = confidence >= self.min_confidence
        return _to_numpy(mask)
