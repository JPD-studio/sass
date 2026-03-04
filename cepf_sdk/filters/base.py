# cepf_sdk/filters/base.py
"""フィルター基底クラス"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

import numpy as np

from cepf_sdk.types import CepfPoints


class FilterMode(Enum):
    """フィルターの動作モード"""
    MASK = "mask"   # 点を削除する
    FLAG = "flag"   # flags にビットを立てる（点は残す）


@dataclass
class FilterResult:
    """フィルター適用結果"""
    points: CepfPoints
    mask: Optional[np.ndarray]
    count_before: int
    count_after: int

    @property
    def removed(self) -> int:
        return self.count_before - self.count_after


class PointFilter(ABC):
    """
    全フィルターの基底クラス。
    サブクラスは compute_mask() だけ実装すればよい。
    """

    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    @abstractmethod
    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """残す点 = True、除去する点 = False の boolean 配列を返す。"""
        ...

    def apply(self, points: CepfPoints) -> FilterResult:
        """共通の適用ロジック（サブクラスはオーバーライド不要）"""
        # 点数を特定
        for v in points.values():
            n_before = len(np.asarray(v))
            break
        else:
            return FilterResult(points=points, mask=None, count_before=0, count_after=0)

        mask = self.compute_mask(points)

        if self.mode == FilterMode.MASK:
            out = _apply_mask(points, mask)
            n_after = int(np.count_nonzero(mask))
        else:
            out = dict(points)
            flags = np.asarray(out.get("flags", np.zeros(n_before, dtype=np.uint16)))
            flags = flags.copy()
            flags[~mask] |= self.flag_bit
            out["flags"] = flags
            n_after = n_before

        return FilterResult(points=out, mask=mask,
                            count_before=n_before, count_after=n_after)


def _apply_mask(points: CepfPoints, mask: np.ndarray) -> CepfPoints:
    """mask=True の点だけ残す"""
    n = len(mask)
    out: Dict[str, np.ndarray] = {}
    for k, v in points.items():
        a = np.asarray(v)
        if a.ndim == 1 and len(a) == n:
            out[k] = a[mask]
        else:
            out[k] = a
    return out
