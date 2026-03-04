# cepf_sdk/filters/attribute/flag.py
"""フラグベースフィルタ"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class FlagFilter(PointFilter):
    """フラグのビットマスクフィルタ"""
    include_flags: int = 0x0000
    exclude_flags: int = 0x0000
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        flags = np.asarray(points.get("flags", np.zeros(0, dtype=np.uint16)))
        mask = np.ones(len(flags), dtype=bool)

        if self.include_flags:
            mask &= (flags & self.include_flags) != 0

        if self.exclude_flags:
            mask &= (flags & self.exclude_flags) == 0

        return mask
