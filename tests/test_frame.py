# tests/test_frame.py
"""CepfFrame / CepfMetadata テスト"""
import json

import numpy as np
import pytest

from cepf_sdk.config import Transform
from cepf_sdk.enums import CoordinateMode, PointFlag
from cepf_sdk.frame import CepfFrame, CepfMetadata


def _make_frame(n: int = 100) -> CepfFrame:
    """テスト用フレーム生成"""
    rng = np.random.default_rng(42)
    metadata = CepfMetadata(
        timestamp_utc="2026-03-03T12:00:00Z",
        frame_id=1,
        coordinate_system="sensor_local",
        coordinate_mode="cartesian",
        units={"position": "meters", "intensity": "normalized"},
    )
    points = {
        "x": rng.uniform(-10, 10, n).astype(np.float32),
        "y": rng.uniform(-10, 10, n).astype(np.float32),
        "z": rng.uniform(-2, 5, n).astype(np.float32),
        "intensity": rng.uniform(0, 1, n).astype(np.float32),
        "flags": np.full(n, PointFlag.VALID, dtype=np.uint16),
    }
    return CepfFrame(
        format="CEPF",
        version="1.4.0",
        metadata=metadata,
        schema={"fields": ["x", "y", "z", "intensity", "flags"],
                "types": ["f32", "f32", "f32", "f32", "u16"]},
        points=points,
        point_count=n,
    )


class TestCepfMetadata:
    def test_frozen(self):
        meta = CepfMetadata(
            timestamp_utc="2026-01-01T00:00:00Z",
            frame_id=1,
            coordinate_system="sensor_local",
            coordinate_mode="cartesian",
            units={},
        )
        with pytest.raises(AttributeError):
            meta.frame_id = 99  # type: ignore[misc]


class TestCepfFrame:
    def test_frozen(self):
        frame = _make_frame()
        with pytest.raises(AttributeError):
            frame.point_count = 0  # type: ignore[misc]

    def test_point_count(self):
        frame = _make_frame(200)
        assert frame.point_count == 200
        assert len(frame.points["x"]) == 200

    def test_to_numpy(self):
        frame = _make_frame()
        d = frame.to_numpy()
        assert "x" in d
        assert isinstance(d["x"], np.ndarray)

    def test_to_json_roundtrip(self):
        frame = _make_frame(10)
        json_str = frame.to_json()
        obj = json.loads(json_str)
        assert obj["format"] == "CEPF"
        assert obj["version"] == "1.4.0"
        assert obj["point_count"] == 10
        assert "x" in obj["points"]

    def test_from_json(self):
        frame = _make_frame(5)
        json_str = frame.to_json()
        restored = CepfFrame.from_json(json_str)
        assert restored.format == "CEPF"
        assert restored.point_count == 5
        np.testing.assert_allclose(
            np.asarray(restored.points["x"]),
            np.asarray(frame.points["x"]),
            atol=1e-4,
        )

    def test_to_binary_header(self):
        frame = _make_frame(10)
        binary = frame.to_binary()
        assert binary[:4] == b"CEPF"
        assert len(binary) >= 32  # header size

    def test_from_binary_header(self):
        frame = _make_frame(10)
        binary = frame.to_binary()
        restored = CepfFrame.from_binary(binary)
        assert restored.format == "CEPF"

    def test_filter_by_flags(self):
        frame = _make_frame(100)
        # Some points flagged as GROUND
        flags = np.asarray(frame.points["flags"]).copy()
        flags[10:30] |= PointFlag.GROUND
        from dataclasses import replace
        frame = replace(frame, points={**frame.points, "flags": flags})

        # Exclude ground
        filtered = frame.filter_by_flags(exclude=PointFlag.GROUND)
        assert filtered.point_count == 80

        # Include only ground
        ground_only = frame.filter_by_flags(include=PointFlag.GROUND)
        assert ground_only.point_count == 20

    def test_transform_points(self):
        frame = _make_frame(50)
        t = Transform(
            translation=np.array([1.0, 2.0, 3.0], dtype=np.float64),
            rotation_quaternion=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
        )
        transformed = frame.transform_points(t)
        # Identity rotation + translation
        np.testing.assert_allclose(
            np.asarray(transformed.points["x"]),
            np.asarray(frame.points["x"]) + 1.0,
            atol=1e-4,
        )
        np.testing.assert_allclose(
            np.asarray(transformed.points["y"]),
            np.asarray(frame.points["y"]) + 2.0,
            atol=1e-4,
        )
        np.testing.assert_allclose(
            np.asarray(transformed.points["z"]),
            np.asarray(frame.points["z"]) + 3.0,
            atol=1e-4,
        )

    def test_transform_empty(self):
        """空の点群に transform しても例外が出ない"""
        meta = CepfMetadata(
            timestamp_utc="", frame_id=0,
            coordinate_system="sensor_local", coordinate_mode="cartesian",
            units={},
        )
        frame = CepfFrame(
            format="CEPF", version="1.4.0", metadata=meta,
            schema={}, points={}, point_count=0,
        )
        t = Transform()
        result = frame.transform_points(t)
        assert result.point_count == 0
