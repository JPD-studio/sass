# tests/test_usc.py
"""UnifiedSenseCloud テスト"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from cepf_sdk.config import InstallationInfo, SensorConfig, Transform
from cepf_sdk.enums import (
    CoordinateMode,
    CoordinateSystem,
    PointFlag,
    SensorType,
)
from cepf_sdk.errors import SensorNotFoundError, ValidationError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.usc import UnifiedSenseCloud


# ---- スタブパーサー ----

class _StubParser(RawDataParser):
    """テスト用の最小パーサー"""

    def parse(self, raw_data, coordinate_mode=None):
        n = 50
        rng = np.random.default_rng(0)
        mode = coordinate_mode or self._default_coordinate_mode
        points = {
            "x": rng.uniform(-5, 5, n).astype(np.float32),
            "y": rng.uniform(-5, 5, n).astype(np.float32),
            "z": rng.uniform(0, 3, n).astype(np.float32),
            "intensity": rng.uniform(0, 1, n).astype(np.float32),
            "flags": np.full(n, PointFlag.VALID, dtype=np.uint16),
        }
        metadata = CepfMetadata(
            timestamp_utc="2026-03-03T00:00:00Z",
            frame_id=self._next_frame_id(),
            coordinate_system="sensor_local",
            coordinate_mode=mode.value if isinstance(mode, CoordinateMode) else str(mode),
            units={"position": "meters"},
            sensor={"type": "lidar", "model": self.config.model},
        )
        return CepfFrame(
            format="CEPF",
            version="1.4.0",
            metadata=metadata,
            schema={"fields": list(points.keys())},
            points=points,
            point_count=n,
        )

    def validate(self, raw_data):
        return isinstance(raw_data, bytes) and len(raw_data) > 0


# ---- テスト ----

class TestUSCBasic:
    def test_add_sensor_and_forge(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="StubLiDAR")
        usc.add_sensor("sensor_a", "_stub", config)

        frame = usc.forge("sensor_a", b"\x01" * 10)
        assert isinstance(frame, CepfFrame)
        assert frame.point_count == 50
        assert frame.format == "CEPF"

    def test_sensor_not_found(self):
        usc = UnifiedSenseCloud()
        with pytest.raises(SensorNotFoundError):
            usc.forge("nonexistent", b"\x00")

    def test_validation_failure(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)

        with pytest.raises(ValidationError):
            usc.forge("s1", b"")  # empty → validate returns False

    def test_fluent_api(self):
        """全メソッドが self を返すことを確認"""
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")

        result = usc.add_sensor("s1", "_stub", config)
        assert result is usc

        result = usc.set_transform([0, 0, 0], [1, 0, 0, 0])
        assert result is usc

        result = usc.set_output_coordinate(CoordinateSystem.SENSOR_LOCAL)
        assert result is usc

        result = usc.set_output_coordinate_mode(CoordinateMode.CARTESIAN)
        assert result is usc

        result = usc.set_installation(InstallationInfo())
        assert result is usc

        result = usc.add_filter(lambda f: f)
        assert result is usc


class TestUSCTransform:
    def test_transform_applied(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)
        usc.set_transform([10.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0])
        usc.set_output_coordinate(CoordinateSystem.WORLD_ENU)

        frame = usc.forge("s1", b"\x01")
        # With identity rotation + [10,0,0] translation, x should be shifted by 10
        assert frame.metadata.coordinate_system == "world_enu"
        assert frame.metadata.transform_to_world is not None


class TestUSCInstallation:
    def test_installation_attached(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)
        usc.set_installation(InstallationInfo(
            reference_description="屋上",
            reference_latitude=35.6762,
            reference_longitude=139.6503,
            reference_altitude=220.5,
        ))

        frame = usc.forge("s1", b"\x01")
        assert frame.metadata.installation is not None
        assert frame.metadata.installation["reference_point"]["latitude"] == 35.6762


class TestUSCFilter:
    def test_filter_applied(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)

        # フィルター: 全点を半分に減らす
        def half_filter(frame: CepfFrame) -> CepfFrame:
            from dataclasses import replace
            half = frame.point_count // 2
            new_points = {k: np.asarray(v)[:half] for k, v in frame.points.items()}
            return replace(frame, points=new_points, point_count=half)

        usc.add_filter(half_filter)
        frame = usc.forge("s1", b"\x01")
        assert frame.point_count == 25


class TestUSCForgeMulti:
    def test_forge_multi(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)
        usc.add_sensor("s2", "_stub", config)

        frame = usc.forge_multi({
            "s1": b"\x01",
            "s2": b"\x02",
        })
        assert frame.point_count == 100  # 50 + 50
        assert len(frame.points["x"]) == 100

    def test_forge_multi_single(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)

        frame = usc.forge_multi({"s1": b"\x01"})
        assert frame.point_count == 50

    def test_forge_multi_empty_raises(self):
        usc = UnifiedSenseCloud()
        with pytest.raises(ValueError):
            usc.forge_multi({})


class TestUSCGetParser:
    def test_get_parser(self):
        usc = UnifiedSenseCloud()
        UnifiedSenseCloud.register_parser("_stub", _StubParser)
        config = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
        usc.add_sensor("s1", "_stub", config)

        parser = usc.get_parser("s1")
        assert isinstance(parser, _StubParser)

    def test_get_parser_none(self):
        usc = UnifiedSenseCloud()
        assert usc.get_parser("missing") is None


class TestUSCFromJSON:
    def test_from_json(self):
        config_dict = {
            "sensors": [
                {
                    "sensor_id": "test_sensor",
                    "parser_name": "_stub",
                    "config": {
                        "sensor_type": "LIDAR",
                        "model": "TestLiDAR",
                    },
                }
            ]
        }
        # _stub パーサーを登録しておく
        UnifiedSenseCloud.register_parser("_stub", _StubParser)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_dict, f)
            f.flush()
            usc = UnifiedSenseCloud.from_json(f.name)

        parser = usc.get_parser("test_sensor")
        assert parser is not None

    def test_from_json_not_found(self):
        with pytest.raises(FileNotFoundError):
            UnifiedSenseCloud.from_json("/tmp/nonexistent_config_xyz.json")
