# cepf_sdk/filters/statistical/ror.py
"""Radius Outlier Removal (ROR) — 距離適応半径 + GPU ブルートフォース対応"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.filters.base import FilterMode, PointFilter
from cepf_sdk.types import CepfPoints

# ================================================================== #
# ハードコード定数 — 用途に合わせてここを変更する                        #
# ================================================================== #

RADIUS_M:       float = 0.3    # 基準近傍探索半径 [m]
MIN_NEIGHBORS:  int   = 5      # 最少近傍点数 (この値未満は除去)
DISTANCE_SCALE: float = 0.0    # 距離適応係数 k（0.0 = 均一半径・後方互換）
                                # r(d) = radius_m × (1 + k × d)
                                # 推奨値: k=0.05～0.15（遠距離での誤除去防止）

# ★ GPU/CPU 選択スイッチ（ここで変更） ★
USE_GPU: bool = False
# 【理由】
# - Ouster OS1-Dome-128: 131K 点/フレーム
#   → 距離行列 O(N²) = 117 GB（Jetson 16GB では不可）
#   → チャンク分割でも CPU cKDTree O(N log N) が優位
# - RoboSense Airy: 10K 点/フレーム
#   → O(N²) と O(N log N) が接近（転送OHが支配）
#   → 統合メモリなら GPU 利得薄い
# 【結論】
# - CPU cKDTree がほぼすべての LiDAR センサーで最適
# - GPU は CuPy インストール後、小規模センサー（<5K 点）専用
# - use_gpu=True にするなら、必ず distance_scale も有効化

GPU_CHUNK_SIZE: int = 4096     # GPU メモリを節約するためのチャンクサイズ（行数）
                                # 使用メモリ ≈ chunk × N × float32(4) bytes
                                # 例: 4096 × 10000 × 4 = 160 MB / チャンク

# ================================================================== #
# 実装ノート
# ================================================================== #
# scipy.cKDTree (CPU ツリー探索 O(N log N)) と
# CuPy ブルートフォース (GPU 距離行列 O(N²)) を自動選択する。
#
# GPU モードは小規模点群 (<5000 点) かつ離散的なクエリに向き、
# LiDAR の密点群フィルタリングには CPU が最適。


def _ror_gpu(
    pts_valid: np.ndarray,
    radii: "np.ndarray | float",
    min_neighbors: int,
    chunk_size: int,
) -> np.ndarray:
    """
    CuPy を使った GPU ブルートフォース ROR。
    pts_valid : shape (M, 3)  NaN 除去済み有効点
    radii     : shape (M,) または スカラー  各点の探索半径
    戻り値    : shape (M,)  bool マスク (True = 保持)
    """
    import cupy as cp

    M = len(pts_valid)
    pts_gpu = cp.asarray(pts_valid, dtype=cp.float32)          # (M, 3)
    radii_gpu = cp.asarray(radii, dtype=cp.float32) if not np.isscalar(radii) \
        else cp.float32(radii)
    counts_gpu = cp.zeros(M, dtype=cp.int32)

    # チャンク処理: i 行目〜i+chunk-1 行目の点をクエリとして全点との距離を計算
    for start in range(0, M, chunk_size):
        end = min(start + chunk_size, M)
        chunk = pts_gpu[start:end]                              # (C, 3)

        # (C, M) の距離行列
        diff = chunk[:, None, :] - pts_gpu[None, :, :]         # (C, M, 3)
        dist = cp.sqrt(cp.sum(diff ** 2, axis=2))              # (C, M)

        if np.isscalar(radii):
            r_chunk = radii_gpu
        else:
            r_chunk = radii_gpu[start:end, None]               # (C, 1)

        counts_gpu[start:end] = cp.sum(dist < r_chunk, axis=1).astype(cp.int32)

    counts = cp.asnumpy(counts_gpu)
    # 自分自身も距離 0 でカウントされるため +1
    return counts >= (min_neighbors + 1)


@dataclass
class RadiusOutlierRemoval(PointFilter):
    """
    半径内の近傍点数が閾値未満の孤立点を除去。

    ── CPU モード（デフォルト）──
    scipy.spatial.cKDTree を使用。ツリー探索のため O(N log N)。

    ── GPU モード（use_gpu=True かつ CuPy インストール済み）──
    CuPy による距離行列ブルートフォース。O(N²) だがチャンク処理でメモリを節約。
    Jetson Orin 統合メモリ環境で 9,500 点/フレーム程度なら CPU より高速。
    CuPy が利用不可の場合は自動で CPU にフォールバックする。

    ── 距離適応半径（distance_scale > 0）──
    LiDAR の点密度は距離の 2 乗に反比例するため、遠距離で探索半径を広げることで
    正常な遠距離点の誤除去を防ぐ。

        r(d) = radius_m × (1 + distance_scale × d)

    距離 d は points["range"] フィールドを優先し、なければ √(x²+y²+z²) で代替。
    distance_scale = 0.0 のとき全点に均一 radius_m を適用（後方互換）。
    """
    radius_m:       float = field(default_factory=lambda: RADIUS_M)
    min_neighbors:  int   = field(default_factory=lambda: MIN_NEIGHBORS)
    distance_scale: float = field(default_factory=lambda: DISTANCE_SCALE)
    use_gpu:        bool  = field(default_factory=lambda: USE_GPU)
    gpu_chunk_size: int   = field(default_factory=lambda: GPU_CHUNK_SIZE)
    mode:     FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        x = np.asarray(points["x"])
        y = np.asarray(points["y"])
        z = np.asarray(points["z"])

        pts = np.stack([x, y, z], axis=-1)

        # NaN を含む点は除去
        valid = ~np.any(np.isnan(pts), axis=1)
        mask = np.zeros(len(x), dtype=bool)

        if np.count_nonzero(valid) == 0:
            return mask

        # --- 探索半径の決定 ---
        if self.distance_scale > 0.0:
            raw_range = points.get("range", None)
            if raw_range is not None:
                d_all = np.asarray(raw_range, dtype=np.float64)
            else:
                d_all = np.linalg.norm(pts, axis=1)
            radii = self.radius_m * (1.0 + self.distance_scale * d_all[valid])
        else:
            radii = self.radius_m  # スカラー → 全点に均一適用

        valid_indices = np.where(valid)[0]

        # --- GPU / CPU を選択 ---
        if self.use_gpu:
            try:
                import cupy as cp
                cp.cuda.runtime.getDeviceCount()  # GPU が存在するか確認
                valid_mask = _ror_gpu(
                    pts[valid].astype(np.float32),
                    radii,
                    self.min_neighbors,
                    self.gpu_chunk_size,
                )
                mask[valid_indices] = valid_mask
                return mask
            except Exception:
                pass  # CuPy 未インストール または GPU なし → CPU にフォールバック

        # --- CPU: scipy cKDTree ---
        from scipy.spatial import cKDTree
        tree = cKDTree(pts[valid])
        counts = tree.query_ball_point(pts[valid], r=radii, return_length=True)
        mask[valid_indices] = np.asarray(counts) >= (self.min_neighbors + 1)
        return mask
