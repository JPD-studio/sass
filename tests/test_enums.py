# tests/test_enums.py
"""Enum テスト"""
import pytest
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, PointFlag, SensorType


class TestSensorType:
    def test_values(self):
        assert SensorType.UNKNOWN.value == 0
        assert SensorType.LIDAR.value == 1
        assert SensorType.RADAR.value == 2

    def test_from_name(self):
        assert SensorType["LIDAR"] is SensorType.LIDAR
        assert SensorType["RADAR"] is SensorType.RADAR


class TestCoordinateSystem:
    def test_string_values(self):
        assert CoordinateSystem.SENSOR_LOCAL == "sensor_local"
        assert CoordinateSystem.VEHICLE_BODY == "vehicle_body"
        assert CoordinateSystem.WORLD_ENU == "world_enu"
        assert CoordinateSystem.WORLD_ECEF == "world_ecef"

    def test_is_str(self):
        assert isinstance(CoordinateSystem.SENSOR_LOCAL, str)


class TestCoordinateMode:
    def test_string_values(self):
        assert CoordinateMode.CARTESIAN == "cartesian"
        assert CoordinateMode.SPHERICAL == "spherical"
        assert CoordinateMode.BOTH == "both"
        assert CoordinateMode.CARTESIAN_WITH_RANGE == "cartesian_with_range"


class TestPointFlag:
    def test_flags_are_powers_of_two(self):
        for flag in PointFlag:
            assert flag.value & (flag.value - 1) == 0, f"{flag} is not a power of 2"

    def test_combine_flags(self):
        combined = PointFlag.VALID | PointFlag.GROUND
        assert combined & PointFlag.VALID
        assert combined & PointFlag.GROUND
        assert not (combined & PointFlag.NOISE)

    def test_specific_bits(self):
        assert PointFlag.VALID == 0x0001
        assert PointFlag.GROUND == 0x0004
        assert PointFlag.NOISE == 0x0010
