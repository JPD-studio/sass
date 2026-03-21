# cepf_sdk/filters/transform/coordinate.py
"""座標変換フィルター — 方位角・仰角回転 + 平行移動"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, FilterResult, PointFilter, _get_xp, _to_numpy
from cepf_sdk.types import CepfPoints

# 座標変換設定値
AZIMUTH_DEG:   float = 0.0   # 方位角 [deg]
ELEVATION_DEG: float = 0.0   # 仰角 [deg]
TX: float = 0.0              # X 方向平行移動 [m]
TY: float = 0.0              # Y 方向平行移動 [m]
TZ: float = 0.0              # Z 方向平行移動 [m]


@dataclass
class CoordinateTransform(PointFilter):
    """
    変換順序:
        1. 仰角回転 
        2. 方位角回転
        3. 平行移動

    変換式:
        R = R_z(azimuth) @ R_y(elevation)
        [x', y', z']ᵀ = R @ [x, y, z]ᵀ + [tx, ty, tz]ᵀ

    球面座標 (azimuth, elevation, range) は直交座標から再計算。

    Args:
        azimuth_deg   : 方位角回転 [deg]。
        elevation_deg : 仰角回転 [deg]。
        tx, ty, tz    : 平行移動 [m]。
        update_spherical : True のとき azimuth/elevation/range フィールドを再計算する。
        mode          : FilterMode.MASK（変換のみ、点の除去なし）
    """

    azimuth_deg:       float = field(default_factory=lambda: AZIMUTH_DEG)
    elevation_deg:     float = field(default_factory=lambda: ELEVATION_DEG)
    tx:                float = field(default_factory=lambda: TX)
    ty:                float = field(default_factory=lambda: TY)
    tz:                float = field(default_factory=lambda: TZ)
    update_spherical:  bool  = True
    mode:              FilterMode = FilterMode.MASK
    flag_bit:          int = 0x0000

    # 回転行列
    _R: np.ndarray = field(init=False, repr=False, compare=False)
    _t: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        az = np.deg2rad(self.azimuth_deg)
        el = np.deg2rad(self.elevation_deg)

        # Y軸回り（仰角）
        R_y = np.array([
            [ np.cos(el), 0.0, np.sin(el)],
            [ 0.0,        1.0, 0.0       ],
            [-np.sin(el), 0.0, np.cos(el)],
        ], dtype=np.float32)

        # Z軸回り（方位角）
        R_z = np.array([
            [np.cos(az), -np.sin(az), 0.0],
            [np.sin(az),  np.cos(az), 0.0],
            [0.0,         0.0,        1.0],
        ], dtype=np.float32)

        self._R = (R_z @ R_y).astype(np.float32)           # 3×3行列
        self._t = np.array([self.tx, self.ty, self.tz],
                           dtype=np.float32)                # 3要素ベクトル

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """座標変換は点を除去しない。全点 True のマスク"""
        for v in points.values():
            return np.ones(len(np.asarray(v)), dtype=bool)
        return np.ones(0, dtype=bool)

    def apply(self, points: CepfPoints) -> FilterResult:
        """直交座標および球面座標を変換して全点を返す。"""
        for v in points.values():
            n = len(np.asarray(v))
            break
        else:
            return FilterResult(points=points, mask=None, count_before=0, count_after=0)

        xp = _get_xp()

        x = xp.asarray(points["x"], dtype=xp.float32)
        y = xp.asarray(points["y"], dtype=xp.float32)
        z = xp.asarray(points["z"], dtype=xp.float32)

        # N×3行列に積み上げて一括行列積
        pts = xp.stack([x, y, z], axis=1)          # N×3行列
        R   = xp.asarray(self._R)                   # 3×3行列
        t   = xp.asarray(self._t)                   # 3要素ベクトル

        pts_out = pts @ R.T + t                     # N×3行列

        out = dict(points)
        out["x"] = _to_numpy(pts_out[:, 0])
        out["y"] = _to_numpy(pts_out[:, 1])
        out["z"] = _to_numpy(pts_out[:, 2])

        # 球面座標の再計算
        if self.update_spherical and "azimuth" in out:
            x_np = out["x"]
            y_np = out["y"]
            z_np = out["z"]
            horiz = np.sqrt(x_np**2 + y_np**2)
            out["azimuth"]   = np.rad2deg(np.arctan2(y_np, x_np)).astype(np.float32)
            out["elevation"] = np.rad2deg(np.arctan2(z_np, horiz)).astype(np.float32)
            if "range" in out:
                out["range"] = np.sqrt(x_np**2 + y_np**2 + z_np**2).astype(np.float32)

        return FilterResult(points=out, mask=None,
                            count_before=n, count_after=n)
