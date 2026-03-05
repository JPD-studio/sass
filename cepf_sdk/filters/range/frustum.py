# cepf_sdk/filters/range/frustum.py
"""円錐台（Frustum）フィルター

Z 軸に直立した円錐台の内側にある点を抽出する。
ドローン離着陸パッドの上空監視を想定した設計。

LiDAR 座標系（センサー原点 z=0）での幅広が長さ z に応じて線形補間される。

設計根拠（確定次第変更予定）:
    - LiDAR 設置高度：離着陸面から約1.0m（マスト高さ未確定）
    - 監視高度範囲：离着陸面上0m 〜 30m
    - LiDAR自身の高さ（z=0）での直径1： 3550mm（3500mm + 50mm マージン）
    - LiDARから 29m上（離着陸面から 30m）での直径1： 5000mm
    - 1m 上がるごとに直径 +50mm（半径 +25mm/m）
    - 実計偈 (3390mm)より少し広めに設定／ PDさん確認済み

1) 実計値の記録:
    离着陸面上の下側直径 = 3390mm（実計）
    上側直径          = 4950mm（実計）
2) 設定値（安全側劇り丸め）:
    r_bottom = 1.775m（直径 3550mm / 2）← LiDAR 高さ z=0 での半径
    r_top    = 2.5m  （直径 5000mm / 2）← z=29m での半径
    height   = 29.0m （LiDARから 30m - 1m = 29m）
    z_bottom = 0.0m  （LiDAR 高度を監視底面に設定）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints

# ================================================================== #
# ハードコード定数 — LiDARマスト高度確定後にここを変更する          #
# ================================================================== #
#
# 座標系: LiDAR センサー原点（z=0）を基準としたセンサーローカル座標
#
#   z = 0       ... LiDAR 設置高度（離着陸面から約1.0m）
#   z = -1.0    ... 離着陸面（LiDARから見て下）
#   z = +29.0   ... 離着陸面から 30m 上空（監視上限）
#
#   z=+29m  r=2.5m  直径=5000mm (実計:4950mm)
#              _______________
#              \  +25mm/m    /
#               \           /
#                \         /
#   z=0           \_______/   r=1.775m  直径=3550mm (= 3390mm + 160mm マージン)
#   ------ LiDAR 高度 ------- z=0
#   z=-1m   r=1.750m  直径=3500mm (実計:3390mmより広め)
#   ====== 離着陸面 =========

R_BOTTOM: float = 1.775   # LiDAR 高度（z=0）での半径 [m]
                          # 実計値: 直径 3390mm → 安全側劇り 3550mm（+160mm）
R_TOP:    float = 2.5     # z=+29m（離着陸面から 30m）での半径 [m]
                          # 実計値: 直径 4950mm → 安全側劇り 5000mm（+50mm）
HEIGHT:   float = 29.0   # 円錐台の高さ [m]
                          # 離着陸面から 30m - LiDAR 高さ 1m = 29m
Z_BOTTOM: float = 0.0    # 円錐台底面の Z 座標 [m]
                          # LiDAR 高度（z=0）を底面に設定
                          # 離着陸面まで含めたい場合は z_bottom=-1.0 に変更

# ------------------------------------------------------------------ #
# GPU / CPU 自動選択                                                    #
# ------------------------------------------------------------------ #

def _get_xp():
    """CuPy が利用可能な場合は cupy を、そうでなければ numpy を返す。"""
    try:
        import cupy as cp
        cp.cuda.runtime.getDeviceCount()   # 実際に GPU があるか確認
        return cp
    except Exception:
        import numpy as np
        return np


# ------------------------------------------------------------------ #
# FrustumFilter                                                        #
# ------------------------------------------------------------------ #

@dataclass
class FrustumFilter(PointFilter):
    """
    Z 軸に直立した円錐台（Frustum）フィルター。

    円錐台の定義:
        ・軸は Z 軸（センサーローカル座標の上下方向）
        ・下側の円: z = z_bottom、半径 = r_bottom
        ・上側の円: z = z_bottom + height、半径 = r_top
        ・高さ方向に半径が線形補間される

    ある点 (x, y, z) が円錐台内部にある条件:
        1. z_bottom <= z <= z_bottom + height
        2. sqrt(x² + y²) <= r_bottom + (r_top - r_bottom) * (z - z_bottom) / height

    Args:
        r_bottom : 下側の円の半径 [m]。デフォルトは定数 R_BOTTOM。
        r_top    : 上側の円の半径 [m]。デフォルトは定数 R_TOP。
        height   : 円錐台の高さ  [m]。デフォルトは定数 HEIGHT。
        z_bottom : 下側の円の Z 座標 [m]。デフォルトは定数 Z_BOTTOM。
        invert   : True にすると円錐台の外側を残す。
        mode     : FilterMode.MASK（点削除）または FilterMode.FLAG（フラグ付け）。
        flag_bit : FLAG モード時に立てるビット。
    """

    r_bottom: float = field(default_factory=lambda: R_BOTTOM)
    r_top:    float = field(default_factory=lambda: R_TOP)
    height:   float = field(default_factory=lambda: HEIGHT)
    z_bottom: float = field(default_factory=lambda: Z_BOTTOM)
    invert:   bool  = False
    mode:     FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints):
        xp = _get_xp()

        x = xp.asarray(points["x"], dtype=xp.float32)
        y = xp.asarray(points["y"], dtype=xp.float32)
        z = xp.asarray(points["z"], dtype=xp.float32)

        z_top = self.z_bottom + self.height

        # ① 高さ範囲チェック
        in_range = (z >= self.z_bottom) & (z <= z_top)

        # ② 高さに応じた半径を線形補間（height=0 の場合は底部半径を使用）
        if self.height > 0.0:
            t = (z - self.z_bottom) / self.height          # 0.0（下端）〜 1.0（上端）
            r_at_z = self.r_bottom + (self.r_top - self.r_bottom) * t
        else:
            r_at_z = xp.full_like(z, self.r_bottom)

        # ③ 水平距離チェック（r_at_z は負になりうるのでクリップ）
        r_at_z = xp.maximum(r_at_z, 0.0)
        horiz2 = x * x + y * y
        in_cone = horiz2 <= r_at_z * r_at_z

        mask = in_range & in_cone

        if self.invert:
            mask = ~mask

        # CuPy の場合は numpy に戻す
        try:
            import cupy as cp
            if isinstance(mask, cp.ndarray):
                mask = cp.asnumpy(mask)
        except ImportError:
            pass

        return mask
