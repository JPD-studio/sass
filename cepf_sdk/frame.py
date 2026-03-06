# cepf_sdk/frame.py
"""CepfFrame / CepfMetadata データクラス (v1.4)"""
from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np

from cepf_sdk.enums import (
    CoordinateMode,
    CoordinateSystem,
    PointFlag,
    SensorType,
)
from cepf_sdk.types import CepfPoints


@dataclass(frozen=True)
class CepfMetadata:
    """フレームメタデータ"""
    timestamp_utc: str
    frame_id: int
    coordinate_system: str
    coordinate_mode: str
    units: Dict[str, str]
    sensor: Optional[Dict[str, Any]] = None
    transform_to_world: Optional[Dict[str, Any]] = None
    installation: Optional[Dict[str, Any]] = None
    extra: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CepfFrame:
    """1フレーム分の点群データ"""
    format: str
    version: str
    metadata: CepfMetadata
    schema: Dict[str, Any]
    points: CepfPoints
    point_count: int
    extensions: Optional[Dict[str, Any]] = None

    def to_numpy(self) -> Dict[str, np.ndarray]:
        """NumPy 配列辞書で返す"""
        return dict(self.points)

    def to_json(self, indent: int = 2) -> str:
        """CEPF JSON 文字列を返す"""
        pts_dict: Dict[str, Any] = {}
        for k, v in self.points.items():
            arr = np.asarray(v)
            if arr.dtype.kind == 'f':
                pts_dict[k] = [None if np.isnan(x) else float(x) for x in arr]
            else:
                pts_dict[k] = arr.tolist()

        obj = {
            "format": self.format,
            "version": self.version,
            "metadata": {
                "timestamp_utc": self.metadata.timestamp_utc,
                "frame_id": self.metadata.frame_id,
                "sensor": self.metadata.sensor,
                "coordinate_system": self.metadata.coordinate_system,
                "coordinate_mode": self.metadata.coordinate_mode,
                "transform_to_world": self.metadata.transform_to_world,
                "units": self.metadata.units,
                "installation": self.metadata.installation,
            },
            "schema": self.schema,
            "points": pts_dict,
            "point_count": self.point_count,
            "extensions": self.extensions,
        }
        return json.dumps(obj, indent=indent, ensure_ascii=False)

    def to_binary(self) -> bytes:
        """CEPF バイナリ形式を返す"""
        mode_str = self.metadata.coordinate_mode
        mode_map = {"cartesian": 0, "spherical": 1, "both": 2, "cartesian_with_range": 3}
        coord_mode_val = mode_map.get(mode_str, 0)

        sensor_type_map = {"lidar": 1, "radar": 2}
        sensor_type_val = 0
        if self.metadata.sensor and "type" in self.metadata.sensor:
            sensor_type_val = sensor_type_map.get(self.metadata.sensor["type"], 0)

        coord_sys_map = {"sensor_local": 0, "vehicle_body": 1, "world_enu": 2, "world_ecef": 3}
        coord_sys_val = coord_sys_map.get(self.metadata.coordinate_system, 0)

        header_flags = 0
        if "velocity" in self.points:
            header_flags |= 0x0001
        if self.extensions:
            header_flags |= 0x0002
        if self.metadata.installation:
            header_flags |= 0x0004

        # Parse timestamp
        ts_ns = 0
        try:
            dt = datetime.fromisoformat(
                self.metadata.timestamp_utc.replace("Z", "+00:00")
            )
            ts_ns = int(dt.timestamp() * 1e9)
        except (ValueError, AttributeError):
            pass

        # Parse version
        parts = self.version.split(".")
        v_major = int(parts[0]) if len(parts) > 0 else 1
        v_minor = int(parts[1]) if len(parts) > 1 else 4

        # Header (32 bytes)
        header = struct.pack(
            "<4sHHBBHIQIBBBB",
            b"CEPF",
            v_major,
            v_minor,
            sensor_type_val,
            coord_sys_val,
            header_flags,
            self.point_count,
            ts_ns,
            self.metadata.frame_id,
            coord_mode_val,
            0, 0, 0,  # reserved
        )

        # Point data
        point_data = bytearray()
        n = self.point_count
        for i in range(n):
            if coord_mode_val == 0:  # CARTESIAN
                point_data += struct.pack(
                    "<ffffffff HBB",
                    float(self.points.get("x", np.zeros(1))[i] if i < len(self.points.get("x", [])) else 0),
                    float(self.points.get("y", np.zeros(1))[i] if i < len(self.points.get("y", [])) else 0),
                    float(self.points.get("z", np.zeros(1))[i] if i < len(self.points.get("z", [])) else 0),
                    float(self.points.get("intensity", np.zeros(1))[i] if i < len(self.points.get("intensity", [])) else 0),
                    float(self.points.get("velocity", np.full(1, np.nan))[i] if i < len(self.points.get("velocity", [])) else float('nan')),
                    float(self.points.get("confidence", np.ones(1))[i] if i < len(self.points.get("confidence", [])) else 1.0),
                    0, 0,  # padding for alignment
                    int(self.points.get("flags", np.zeros(1, dtype=np.uint16))[i] if i < len(self.points.get("flags", [])) else 0),
                    int(self.points.get("return_id", np.zeros(1, dtype=np.uint8))[i] if i < len(self.points.get("return_id", [])) else 0),
                    0,  # reserved
                )
            elif coord_mode_val == 2:  # BOTH
                point_data += struct.pack(
                    "<ffffffffff HBB",
                    float(self.points.get("x", np.zeros(1))[i] if i < len(self.points.get("x", [])) else 0),
                    float(self.points.get("y", np.zeros(1))[i] if i < len(self.points.get("y", [])) else 0),
                    float(self.points.get("z", np.zeros(1))[i] if i < len(self.points.get("z", [])) else 0),
                    float(self.points.get("azimuth", np.zeros(1))[i] if i < len(self.points.get("azimuth", [])) else 0),
                    float(self.points.get("elevation", np.zeros(1))[i] if i < len(self.points.get("elevation", [])) else 0),
                    float(self.points.get("range", np.zeros(1))[i] if i < len(self.points.get("range", [])) else 0),
                    float(self.points.get("intensity", np.zeros(1))[i] if i < len(self.points.get("intensity", [])) else 0),
                    float(self.points.get("velocity", np.full(1, np.nan))[i] if i < len(self.points.get("velocity", [])) else float('nan')),
                    float(self.points.get("confidence", np.ones(1))[i] if i < len(self.points.get("confidence", [])) else 1.0),
                    0,  # padding
                    int(self.points.get("flags", np.zeros(1, dtype=np.uint16))[i] if i < len(self.points.get("flags", [])) else 0),
                    int(self.points.get("return_id", np.zeros(1, dtype=np.uint8))[i] if i < len(self.points.get("return_id", [])) else 0),
                    0,  # reserved
                )

        return bytes(header) + bytes(point_data)

    @classmethod
    def from_json(cls, json_str: str) -> CepfFrame:
        """JSON 文字列から CepfFrame を生成"""
        from cepf_sdk.errors import SerializationError
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise SerializationError(f"JSON parse error: {e}") from e

        meta_obj = obj.get("metadata", {})
        metadata = CepfMetadata(
            timestamp_utc=meta_obj.get("timestamp_utc", ""),
            frame_id=meta_obj.get("frame_id", 0),
            coordinate_system=meta_obj.get("coordinate_system", "sensor_local"),
            coordinate_mode=meta_obj.get("coordinate_mode", "cartesian"),
            units=meta_obj.get("units", {}),
            sensor=meta_obj.get("sensor"),
            transform_to_world=meta_obj.get("transform_to_world"),
            installation=meta_obj.get("installation"),
        )

        raw_points = obj.get("points", {})
        points: CepfPoints = {}
        type_map = {
            "x": np.float32, "y": np.float32, "z": np.float32,
            "azimuth": np.float32, "elevation": np.float32, "range": np.float32,
            "timestamp": np.float64,
            "intensity": np.float32, "velocity": np.float32, "confidence": np.float32,
            "return_id": np.uint8, "flags": np.uint16,
        }
        for k, v in raw_points.items():
            dtype = type_map.get(k, np.float32)
            if dtype in (np.float32, np.float64):
                arr = np.array([float('nan') if x is None else x for x in v], dtype=dtype)
            else:
                arr = np.array(v, dtype=dtype)
            points[k] = arr  # type: ignore[literal-required]

        return cls(
            format=obj.get("format", "CEPF"),
            version=obj.get("version", "1.4.0"),
            metadata=metadata,
            schema=obj.get("schema", {}),
            points=points,
            point_count=obj.get("point_count", 0),
            extensions=obj.get("extensions"),
        )

    @classmethod
    def from_binary(cls, data: bytes) -> CepfFrame:
        """バイナリデータから CepfFrame を生成"""
        from cepf_sdk.errors import SerializationError
        if len(data) < 32:
            raise SerializationError("Binary data too short for CEPF header")
        magic = data[0:4]
        if magic != b"CEPF":
            raise SerializationError(f"Invalid magic: {magic!r}")

        v_major, v_minor = struct.unpack_from("<HH", data, 4)
        sensor_type_val = data[8]
        coord_sys_val = data[9]
        header_flags = struct.unpack_from("<H", data, 10)[0]
        point_count = struct.unpack_from("<I", data, 12)[0]
        ts_ns = struct.unpack_from("<Q", data, 16)[0]
        frame_id = struct.unpack_from("<I", data, 24)[0]
        coord_mode_val = data[28]

        sensor_type_names = {0: "unknown", 1: "lidar", 2: "radar"}
        coord_sys_names = {0: "sensor_local", 1: "vehicle_body", 2: "world_enu", 3: "world_ecef"}
        coord_mode_names = {0: "cartesian", 1: "spherical", 2: "both", 3: "cartesian_with_range"}

        ts_utc = ""
        if ts_ns > 0:
            dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
            ts_utc = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        metadata = CepfMetadata(
            timestamp_utc=ts_utc,
            frame_id=frame_id,
            coordinate_system=coord_sys_names.get(coord_sys_val, "sensor_local"),
            coordinate_mode=coord_mode_names.get(coord_mode_val, "cartesian"),
            units={"position": "meters", "velocity": "m/s", "angle": "degrees", "intensity": "normalized"},
            sensor={"type": sensor_type_names.get(sensor_type_val, "unknown")},
        )

        # Parse point data based on coordinate_mode
        points: CepfPoints = {}
        offset = 32
        # Simplified: read cartesian points (28 bytes each)
        if coord_mode_val == 0 and point_count > 0:
            for _ in range(point_count):
                if offset + 28 > len(data):
                    break
                # Read individual point fields...
                offset += 28

        return cls(
            format="CEPF",
            version=f"{v_major}.{v_minor}.0",
            metadata=metadata,
            schema={},
            points=points,
            point_count=point_count,
        )

    def filter_by_flags(self, include: int = 0, exclude: int = 0) -> CepfFrame:
        """フラグでフィルタした新フレームを返す"""
        flags = np.asarray(self.points.get("flags", np.zeros(self.point_count, dtype=np.uint16)))
        mask = np.ones(self.point_count, dtype=bool)
        if include:
            mask &= (flags & include) != 0
        if exclude:
            mask &= (flags & exclude) == 0

        new_points: CepfPoints = {}
        for k, v in self.points.items():
            arr = np.asarray(v)
            if arr.ndim == 1 and len(arr) == self.point_count:
                new_points[k] = arr[mask]  # type: ignore[literal-required]
            else:
                new_points[k] = arr  # type: ignore[literal-required]

        new_count = int(np.count_nonzero(mask))
        return replace(self, points=new_points, point_count=new_count)

    def transform_points(self, transform: Any) -> CepfFrame:
        """座標変換を適用した新フレームを返す"""
        M = transform.to_matrix()
        R = M[:3, :3]
        t = M[:3, 3]

        x = np.asarray(self.points.get("x", np.zeros(0, dtype=np.float32)))
        y = np.asarray(self.points.get("y", np.zeros(0, dtype=np.float32)))
        z = np.asarray(self.points.get("z", np.zeros(0, dtype=np.float32)))

        if x.size == 0:
            return self

        pts = np.stack([x, y, z], axis=-1)  # (N, 3)
        transformed = (pts @ R.T + t).astype(np.float32)

        new_points = dict(self.points)
        new_points["x"] = transformed[:, 0]
        new_points["y"] = transformed[:, 1]
        new_points["z"] = transformed[:, 2]
        return replace(self, points=new_points)
