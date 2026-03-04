# tests/test_filters/test_pipeline.py
"""FilterPipeline テスト"""
from __future__ import annotations

import numpy as np
import pytest

from cepf_sdk.filters.base import FilterMode
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.range.box import BoxFilter
from cepf_sdk.filters.attribute.intensity import IntensityFilter
from cepf_sdk.types import CepfPoints


def _make_points(n: int = 500) -> CepfPoints:
    rng = np.random.default_rng(42)
    return {
        "x": rng.uniform(-20, 20, n).astype(np.float32),
        "y": rng.uniform(-20, 20, n).astype(np.float32),
        "z": rng.uniform(-5, 30, n).astype(np.float32),
        "intensity": rng.uniform(0, 1, n).astype(np.float32),
    }


class TestFilterPipeline:
    def test_empty_pipeline(self):
        pts = _make_points(100)
        pipeline = FilterPipeline(filters=[])
        result = pipeline.apply(pts)
        assert result.count_after == 100

    def test_single_filter(self):
        pts = _make_points(500)
        pipeline = FilterPipeline(filters=[
            CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0),
        ])
        result = pipeline.apply(pts)
        assert result.count_after < 500

    def test_chained_filters(self):
        """複数フィルターを連鎖して適用"""
        pts = _make_points(500)
        pipeline = FilterPipeline(filters=[
            BoxFilter(x_min=-10, x_max=10, y_min=-10, y_max=10, z_min=-10, z_max=30),
            IntensityFilter(min_intensity=0.3, max_intensity=0.8),
        ])
        result = pipeline.apply(pts)
        # 両方のフィルタで絞られる
        assert result.count_after < 500

    def test_verbose_mode(self, capsys):
        pts = _make_points(100)
        pipeline = FilterPipeline(
            filters=[
                CylindricalFilter(radius_m=100.0, z_min_m=-100.0, z_max_m=100.0),
            ],
            verbose=True,
        )
        pipeline.apply(pts)
        captured = capsys.readouterr()
        assert "CylindricalFilter" in captured.out

    def test_empty_points(self):
        pts: CepfPoints = {}
        pipeline = FilterPipeline(filters=[
            CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0),
        ])
        result = pipeline.apply(pts)
        assert result.count_after == 0
