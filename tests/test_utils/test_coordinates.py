# tests/test_utils/test_coordinates.py
"""座標変換ユーティリティのテスト"""
from __future__ import annotations

import math

import pytest

from cepf_sdk.utils.coordinates import (
    cartesian_to_spherical,
    ecef_to_lla,
    lla_to_ecef,
    spherical_to_cartesian,
)


class TestSphericalCartesian:
    def test_identity(self):
        """(range=1, az=0, el=0) → (1, 0, 0)"""
        x, y, z = spherical_to_cartesian(1.0, 0.0, 0.0)
        assert abs(x - 1.0) < 1e-10
        assert abs(y) < 1e-10
        assert abs(z) < 1e-10

    def test_azimuth_90(self):
        """az=90° → y方向"""
        x, y, z = spherical_to_cartesian(1.0, 90.0, 0.0)
        assert abs(x) < 1e-10
        assert abs(y - 1.0) < 1e-10

    def test_elevation_90(self):
        """el=90° → z方向"""
        x, y, z = spherical_to_cartesian(1.0, 0.0, 90.0)
        assert abs(x) < 1e-10
        assert abs(y) < 1e-10
        assert abs(z - 1.0) < 1e-10

    def test_roundtrip(self):
        """球面 → 直交 → 球面 の往復"""
        r, az, el = 5.0, 45.0, 30.0
        x, y, z = spherical_to_cartesian(r, az, el)
        r2, az2, el2 = cartesian_to_spherical(x, y, z)
        assert abs(r - r2) < 1e-8
        assert abs(az - az2) < 1e-8
        assert abs(el - el2) < 1e-8

    def test_multiple_angles(self):
        for az in [0, 45, 90, 135, 180, -45, -90, -135]:
            for el in [-30, 0, 15, 45, 60]:
                x, y, z = spherical_to_cartesian(10.0, az, el)
                r2, az2, el2 = cartesian_to_spherical(x, y, z)
                assert abs(10.0 - r2) < 1e-6
                # 方位角は atan2 の範囲 (-180, 180] に正規化されるのでモジュロ比較
                az_normalized = ((az + 180) % 360) - 180
                az2_normalized = ((az2 + 180) % 360) - 180
                assert abs(az_normalized - az2_normalized) < 1e-6
                assert abs(el - el2) < 1e-6


class TestLLAtoECEF:
    def test_equator_prime_meridian(self):
        """赤道/本初子午線 → X軸方向"""
        x, y, z = lla_to_ecef(0.0, 0.0, 0.0)
        assert abs(y) < 1e-3
        assert abs(z) < 1e-3
        # 赤道半径 ≈ 6378137 m
        assert abs(x - 6378137.0) < 1.0

    def test_north_pole(self):
        """北極"""
        x, y, z = lla_to_ecef(90.0, 0.0, 0.0)
        assert abs(x) < 1e-3
        assert abs(y) < 1e-3
        # 極半径 ≈ 6356752 m
        assert abs(z - 6356752.3) < 1.0

    def test_roundtrip(self):
        """LLA → ECEF → LLA の往復"""
        lat, lon, alt = 35.6762, 139.6503, 220.5
        x, y, z = lla_to_ecef(lat, lon, alt)
        lat2, lon2, alt2 = ecef_to_lla(x, y, z)
        assert abs(lat - lat2) < 1e-8
        assert abs(lon - lon2) < 1e-8
        assert abs(alt - alt2) < 0.01  # mm 精度

    def test_roundtrip_southern_hemisphere(self):
        lat, lon, alt = -33.8688, 151.2093, 50.0  # Sydney
        x, y, z = lla_to_ecef(lat, lon, alt)
        lat2, lon2, alt2 = ecef_to_lla(x, y, z)
        assert abs(lat - lat2) < 1e-8
        assert abs(lon - lon2) < 1e-8
        assert abs(alt - alt2) < 0.01
