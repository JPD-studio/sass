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
