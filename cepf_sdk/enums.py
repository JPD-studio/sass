# cepf_sdk/enums.py
"""CEPF/USC 列挙型定義 (v1.4)"""
from __future__ import annotations

from enum import Enum, IntFlag


class SensorType(Enum):
    """センサー種別"""
    UNKNOWN = 0
    LIDAR = 1
    RADAR = 2


class CoordinateSystem(str, Enum):
    """座標系識別子"""
    SENSOR_LOCAL = "sensor_local"
    VEHICLE_BODY = "vehicle_body"
    WORLD_ENU = "world_enu"
    WORLD_ECEF = "world_ecef"


class CoordinateMode(str, Enum):
    """座標表現形式 (v1.1追加)"""
    CARTESIAN = "cartesian"
    SPHERICAL = "spherical"
    BOTH = "both"
    CARTESIAN_WITH_RANGE = "cartesian_with_range"


class PointFlag(IntFlag):
    """点群ビットフラグ"""
    VALID = 0x0001
    DYNAMIC = 0x0002
    GROUND = 0x0004
    SATURATED = 0x0008
    NOISE = 0x0010
    RAIN = 0x0020
    MULTIPATH = 0x0040
    LOW_CONFIDENCE = 0x0080
