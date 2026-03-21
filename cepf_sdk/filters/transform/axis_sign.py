# cepf_sdk/filters/transform/axis_sign.py
"""軸符号変換フィルター

直交座標変換後の x/y/z 軸に対して符号反転（×-1）を適用する。
下向き設置センサー (OS-DOME 天井マウント等) の Z 軸反転に使用。

点の削除は行わない。apply() を完全オーバーライドし、座標変換のみを行う。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cepf_sdk.filters.base import FilterMode, FilterResult, PointFilter
from cepf_sdk.types import CepfPoints


@dataclass
class AxisSignFilter(PointFilter):
    """直交座標変換後の軸符号変換フィルター。

    x_sign / y_sign / z_sign は 1 (正方向維持) または -1 (符号反転) のみ有効。
    点の削除は行わない（座標変換のみ）。apply() を完全オーバーライドする。
    """
    x_sign: int = 1
    y_sign: int = 1
    z_sign: int = 1

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """PointFilter の抽象メソッドを満たすダミー実装（実際には呼ばれない）。"""
        for v in points.values():
            return np.ones(len(np.asarray(v)), dtype=bool)
        return np.ones(0, dtype=bool)

    def apply(self, points: CepfPoints) -> FilterResult:
        """x/y/z 各軸に sign を乗じる。sign==1 の軸はコピーコストなしスキップ。"""
        n = 0
        for v in points.values():
            n = len(np.asarray(v))
            break
        if n == 0:
            return FilterResult(points=points, mask=None, count_before=0, count_after=0)
        out = dict(points)
        for axis, sign in (("x", self.x_sign), ("y", self.y_sign), ("z", self.z_sign)):
            if sign != 1 and axis in out:
                arr = np.asarray(out[axis])
                out[axis] = (arr * sign).astype(arr.dtype)
        return FilterResult(points=out, mask=None, count_before=n, count_after=n)
