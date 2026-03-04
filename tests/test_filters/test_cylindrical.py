# tests/test_filters/test_cylindrical.py
"""円筒形フィルタのテスト"""
from __future__ import annotations

import numpy as np
import pytest

from cepf_sdk.filters.base import FilterMode
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.types import CepfPoints


def _make_points(n: int = 100) -> CepfPoints:
    rng = np.random.default_rng(42)
    return {
        "x": rng.uniform(-20, 20, n).astype(np.float32),
        "y": rng.uniform(-20, 20, n).astype(np.float32),
        "z": rng.uniform(-5, 30, n).astype(np.float32),
        "intensity": rng.uniform(0, 1, n).astype(np.float32),
    }


class TestCylindricalFilter:
    def test_basic_filter(self):
        pts = _make_points(1000)
        f = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0)
        result = f.apply(pts)
        assert result.count_after <= result.count_before
        assert result.count_after > 0

    def test_very_large_radius(self):
        """巨大な半径 → ほぼ全点が残る (z 範囲内)"""
        pts = _make_points(100)
        f = CylindricalFilter(radius_m=1000.0, z_min_m=-100.0, z_max_m=100.0)
        result = f.apply(pts)
        assert result.count_after == result.count_before

    def test_zero_radius(self):
        """半径0 → ほぼ全点が除去される"""
        pts = _make_points(100)
        f = CylindricalFilter(radius_m=0.0, z_min_m=-100.0, z_max_m=100.0)
        result = f.apply(pts)
        assert result.count_after == 0

    def test_invert(self):
        """invert で外側を残す"""
        pts = _make_points(1000)
        f_normal = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0)
        f_invert = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0, invert=True)

        r_normal = f_normal.apply(pts)
        r_invert = f_invert.apply(pts)
        assert r_normal.count_after + r_invert.count_after == r_normal.count_before

    def test_flag_mode(self):
        """FLAG モードでは点数は変わらない"""
        pts = _make_points(100)
        pts["flags"] = np.zeros(100, dtype=np.uint16)
        f = CylindricalFilter(
            radius_m=5.0, z_min_m=-5.0, z_max_m=30.0,
            mode=FilterMode.FLAG, flag_bit=0x0004,
        )
        result = f.apply(pts)
        assert result.count_after == result.count_before
        flags = np.asarray(result.points["flags"])
        # 領域外の点にフラグが立っている
        assert np.any(flags & 0x0004)

    def test_center_offset(self):
        """中心をオフセットして使用"""
        pts = {
            "x": np.array([10.0, 10.5, 0.0], dtype=np.float32),
            "y": np.array([10.0, 10.5, 0.0], dtype=np.float32),
            "z": np.array([1.0, 1.0, 1.0], dtype=np.float32),
        }
        f = CylindricalFilter(radius_m=1.0, z_min_m=0.0, z_max_m=2.0, cx=10.0, cy=10.0)
        result = f.apply(pts)
        # (10,10) と (10.5,10.5) は半径1内、(0,0) は外
        assert result.count_after == 2
