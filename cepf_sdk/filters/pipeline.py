# cepf_sdk/filters/pipeline.py
"""フィルターパイプライン"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from cepf_sdk.filters.base import FilterResult, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class FilterPipeline:
    """複数フィルターを順番に適用する。"""
    filters: List[PointFilter] = field(default_factory=list)
    verbose: bool = False

    def apply(self, points: CepfPoints) -> FilterResult:
        """全フィルターを順次適用する"""
        current = points

        # 初期点数
        for v in points.values():
            n_original = len(np.asarray(v))
            break
        else:
            return FilterResult(points=points, mask=None, count_before=0, count_after=0)

        for f in self.filters:
            result = f.apply(current)
            if self.verbose:
                name = type(f).__name__
                print(f"  [{name}] {result.count_before} -> {result.count_after}"
                      f" (removed {result.removed})")
            current = result.points

        # 最終点数
        for v in current.values():
            n_final = len(np.asarray(v))
            break
        else:
            n_final = 0

        return FilterResult(points=current, mask=None,
                            count_before=n_original, count_after=n_final)
