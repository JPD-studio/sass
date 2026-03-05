# cepf_sdk/filters/attribute/flag.py
"""フラグベースフィルタ"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# ------------------------------------------------------------------ #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ------------------------------------------------------------------ #

INCLUDE_FLAGS: int = 0x0000  # このビットが立っている点を保持 (0=全て通過)
EXCLUDE_FLAGS: int = 0x0000  # このビットが立っている点を除去 (0=除去なし)


@dataclass
class FlagFilter(PointFilter):
    """フラグのビットマスクフィルタ。CuPy が利用可能な場合は GPU で演算する。"""
    include_flags: int = field(default_factory=lambda: INCLUDE_FLAGS)
    exclude_flags: int = field(default_factory=lambda: EXCLUDE_FLAGS)
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        xp = _get_xp()
        flags = xp.asarray(
            points.get("flags", np.zeros(0, dtype=np.uint16)),
            dtype=xp.uint16,
        )
        mask = xp.ones(len(flags), dtype=bool)

        if self.include_flags:
            mask &= (flags & self.include_flags) != 0

        if self.exclude_flags:
            mask &= (flags & self.exclude_flags) == 0

        return _to_numpy(mask)
