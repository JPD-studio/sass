# tests/test_filters/test_ror.py
"""RadiusOutlierRemoval テスト"""
from __future__ import annotations

import numpy as np
import pytest

from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.types import CepfPoints


def _make_clustered_points() -> CepfPoints:
    """クラスタ + 外れ値の点群を生成"""
    rng = np.random.default_rng(42)
    # 密なクラスタ (80点)
    cx = rng.normal(0, 0.1, 80).astype(np.float32)
    cy = rng.normal(0, 0.1, 80).astype(np.float32)
    cz = rng.normal(0, 0.1, 80).astype(np.float32)
    # 外れ値 (20点)
    ox = rng.uniform(50, 100, 20).astype(np.float32)
    oy = rng.uniform(50, 100, 20).astype(np.float32)
    oz = rng.uniform(50, 100, 20).astype(np.float32)

    return {
        "x": np.concatenate([cx, ox]),
        "y": np.concatenate([cy, oy]),
        "z": np.concatenate([cz, oz]),
        "intensity": np.ones(100, dtype=np.float32),
    }


class TestRadiusOutlierRemoval:
    def test_removes_outliers(self):
        pts = _make_clustered_points()
        f = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3)
        result = f.apply(pts)
        # 外れ値の多くは除去されるはず
        assert result.count_after < 100
        assert result.count_after >= 70  # クラスタの大半は残る

    def test_very_large_radius_keeps_all(self):
        pts = _make_clustered_points()
        f = RadiusOutlierRemoval(radius_m=10000.0, min_neighbors=1)
        result = f.apply(pts)
        assert result.count_after == 100

    def test_empty_points(self):
        pts = {
            "x": np.array([], dtype=np.float32),
            "y": np.array([], dtype=np.float32),
            "z": np.array([], dtype=np.float32),
        }
        f = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3)
        result = f.apply(pts)
        assert result.count_after == 0

    def test_distance_scale_zero_backward_compat(self):
        """distance_scale=0 は従来の固定半径と同じ結果になること"""
        pts = _make_clustered_points()
        f_old = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3, distance_scale=0.0)
        f_new = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3)
        r_old = f_old.apply(pts)
        r_new = f_new.apply(pts)
        assert r_old.count_after == r_new.count_after

    def test_distance_scale_preserves_far_cluster(self):
        """
        distance_scale > 0 のとき、遠距離の正常クラスタが保持されること。
        固定半径では点密度が低い遠距離クラスタを誤除去するが、
        半径を距離スケールすることで正常点が残る。
        """
        rng = np.random.default_rng(0)
        # 近距離クラスタ: 原点付近に 40 点、ばらつき 0.05 m
        near_x = rng.normal(0.0, 0.05, 40).astype(np.float32)
        near_y = rng.normal(0.0, 0.05, 40).astype(np.float32)
        near_z = rng.normal(0.0, 0.05, 40).astype(np.float32)
        # 遠距離クラスタ: (30, 0, 0) 付近に 40 点、ばらつき 1.0 m (密度は低いが正常点)
        far_x = rng.normal(30.0, 1.0, 40).astype(np.float32)
        far_y = rng.normal(0.0, 1.0, 40).astype(np.float32)
        far_z = rng.normal(0.0, 1.0, 40).astype(np.float32)

        pts: CepfPoints = {
            "x": np.concatenate([near_x, far_x]),
            "y": np.concatenate([near_y, far_y]),
            "z": np.concatenate([near_z, far_z]),
        }

        # 固定半径: 遠距離クラスタの点間隔 (~2m) に対して radius_m=0.3 では近傍なし → 誤除去
        f_fixed = RadiusOutlierRemoval(radius_m=0.3, min_neighbors=3, distance_scale=0.0)
        result_fixed = f_fixed.apply(pts)

        # 距離適応 (k=0.07): r(30m) = 0.3 * (1 + 0.07*30) = 0.3 * 3.1 = 0.93 m → 遠距離を保持
        f_adaptive = RadiusOutlierRemoval(radius_m=0.3, min_neighbors=3, distance_scale=0.07)
        result_adaptive = f_adaptive.apply(pts)

        # 適応フィルタは固定フィルタより多くの点を残す（遠距離クラスタが保護される）
        assert result_adaptive.count_after > result_fixed.count_after

    def test_distance_scale_uses_range_field(self):
        """points['range'] フィールドがあればそれを距離として使用すること"""
        rng = np.random.default_rng(1)
        x = rng.normal(0.0, 0.05, 30).astype(np.float32)
        y = rng.normal(0.0, 0.05, 30).astype(np.float32)
        z = rng.normal(0.0, 0.05, 30).astype(np.float32)
        range_vals = np.array([0.0] * 15 + [50.0] * 15, dtype=np.float32)

        pts: CepfPoints = {"x": x, "y": y, "z": z, "range": range_vals}

        f = RadiusOutlierRemoval(radius_m=0.2, min_neighbors=3, distance_scale=0.1)
        result = f.apply(pts)
        assert result.count_after == 30

    def test_use_gpu_false_same_as_cpu(self):
        """use_gpu=False（デフォルト）は CuPy がなくても CPU にフォールバックすること"""
        pts = _make_clustered_points()
        f = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3, use_gpu=False)
        result = f.apply(pts)
        assert result.count_after >= 70

    def test_use_gpu_true_fallback_without_cupy(self):
        """CuPy 未インストール時に use_gpu=True でも scipy フォールバックで動作すること"""
        pts = _make_clustered_points()
        f_cpu = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3, use_gpu=False)
        f_gpu = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3, use_gpu=True)
        # 結果が同一であることを確認（どちらも CPU で動く）
        r_cpu = f_cpu.apply(pts)
        r_gpu = f_gpu.apply(pts)
        assert r_cpu.count_after == r_gpu.count_after

