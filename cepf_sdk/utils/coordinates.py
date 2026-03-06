# cepf_sdk/utils/coordinates.py
"""座標変換ユーティリティ"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np


def spherical_to_cartesian(
    range_m: float, azimuth_deg: float, elevation_deg: float
) -> Tuple[float, float, float]:
    """
    球面座標 → 直交座標

    Parameters
    ----------
    range_m : float
        距離 (m)
    azimuth_deg : float
        方位角 (degrees)
    elevation_deg : float
        仰角 (degrees)

    Returns
    -------
    tuple[float, float, float]
        (x, y, z) in meters
    """
    az_rad = math.radians(azimuth_deg)
    el_rad = math.radians(elevation_deg)
    cos_el = math.cos(el_rad)
    x = range_m * cos_el * math.cos(az_rad)
    y = range_m * cos_el * math.sin(az_rad)
    z = range_m * math.sin(el_rad)
    return (x, y, z)


def cartesian_to_spherical(
    x: float, y: float, z: float
) -> Tuple[float, float, float]:
    """
    直交座標 → 球面座標

    Parameters
    ----------
    x, y, z : float
        直交座標 (m)

    Returns
    -------
    tuple[float, float, float]
        (range_m, azimuth_deg, elevation_deg)
    """
    range_m = math.sqrt(x * x + y * y + z * z)
    azimuth_deg = math.degrees(math.atan2(y, x))
    elevation_deg = math.degrees(math.atan2(z, math.sqrt(x * x + y * y))) if range_m > 1e-12 else 0.0
    return (range_m, azimuth_deg, elevation_deg)


# WGS84 楕円体パラメータ
_WGS84_A = 6378137.0           # 赤道半径 (m)
_WGS84_F = 1.0 / 298.257223563  # 扁平率
_WGS84_B = _WGS84_A * (1.0 - _WGS84_F)  # 極半径
_WGS84_E2 = 2.0 * _WGS84_F - _WGS84_F * _WGS84_F  # 第一離心率の2乗


def lla_to_ecef(
    lat: float, lon: float, alt: float
) -> Tuple[float, float, float]:
    """
    WGS84 緯度経度高度 → ECEF (v1.1追加)

    Parameters
    ----------
    lat : float
        緯度 (degrees, 北緯正)
    lon : float
        経度 (degrees, 東経正)
    alt : float
        WGS84 楕円体高 (m)

    Returns
    -------
    tuple[float, float, float]
        (x, y, z) in ECEF meters
    """
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    sin_lon = math.sin(lon_rad)
    cos_lon = math.cos(lon_rad)

    N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)

    x = (N + alt) * cos_lat * cos_lon
    y = (N + alt) * cos_lat * sin_lon
    z = (N * (1.0 - _WGS84_E2) + alt) * sin_lat
    return (x, y, z)


def ecef_to_lla(
    x: float, y: float, z: float
) -> Tuple[float, float, float]:
    """
    ECEF → WGS84 緯度経度高度 (v1.1追加)
    Bowring iterative method.

    Parameters
    ----------
    x, y, z : float
        ECEF 座標 (m)

    Returns
    -------
    tuple[float, float, float]
        (lat_deg, lon_deg, alt_m)
    """
    lon = math.atan2(y, x)
    p = math.sqrt(x * x + y * y)

    # Initial estimate
    lat = math.atan2(z, p * (1.0 - _WGS84_E2))

    for _ in range(10):
        sin_lat = math.sin(lat)
        N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
        lat_new = math.atan2(z + _WGS84_E2 * N * sin_lat, p)
        if abs(lat_new - lat) < 1e-12:
            break
        lat = lat_new

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)

    if abs(cos_lat) > 1e-10:
        alt = p / cos_lat - N
    else:
        alt = abs(z) / abs(sin_lat) - N * (1.0 - _WGS84_E2)

    return (math.degrees(lat), math.degrees(lon), alt)
