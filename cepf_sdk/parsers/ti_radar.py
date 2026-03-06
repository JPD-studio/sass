# cepf_sdk/parsers/ti_radar.py
"""Texas Instruments AWR/IWR mmWave シリーズ用パーサー"""
from __future__ import annotations

import struct
import time

import numpy as np

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, PointFlag, SensorType
from cepf_sdk.errors import ParseError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints

# TI mmWave Out-of-Box demo パケット仕様
MAGIC_WORD = b'\x02\x01\x04\x03\x06\x05\x08\x07'
HEADER_SIZE = 40          # 8 bytes magic + 8 * uint32
TLV_HEADER_SIZE = 8       # type(uint32) + length(uint32)
TLV_TYPE_DETECTED_POINTS = 1   # XYZ + Doppler velocity per point
TLV_TYPE_SIDE_INFO = 7         # SNR + noise per point (4 bytes each)
POINT_STRUCT_SIZE = 16    # float x, y, z, doppler
SIDE_INFO_STRUCT_SIZE = 4 # int16 snr, int16 noise


class TIRadarParser(RawDataParser):
    """
    Texas Instruments AWR1843, IWR6843 mmWave 用パーサー。

    TI Out-of-Box デモのバイナリプロトコルを解析する:
      - Header (40 bytes): magic word + 8 x uint32
      - TLV records: Type 1 (point cloud XYZ+Doppler), Type 7 (SNR side info)
    """

    def __init__(self, config: SensorConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.RADAR,
                model="TI AWR1843",
                max_range_m=50.0,
            )
        super().__init__(config)
        self.velocity_offset: float = 0.0

    def set_ego_velocity(self, velocity_mps: float) -> None:
        """自車速度設定 (Doppler 補正用)"""
        self.velocity_offset = velocity_mps

    def validate(self, raw_data: bytes) -> bool:
        return (
            len(raw_data) >= HEADER_SIZE
            and raw_data[:len(MAGIC_WORD)] == MAGIC_WORD
        )

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        if not self.validate(raw_data):
            raise ParseError("無効な TI Radar パケット (マジックワード不一致またはデータ不足)")

        # Header layout (after 8-byte magic):
        # version, totalPacketLen, platform, frameNumber,
        # timeCpuCycles, numDetectedObj, numTLVs, subFrameNumber
        (version, total_len, platform, frame_num,
         cpu_cycles, num_obj, num_tlvs, subframe_num) = struct.unpack_from(
            '<IIIIIIII', raw_data, 8
        )

        if len(raw_data) < total_len:
            raise ParseError(
                f"データが短すぎます (got {len(raw_data)}, expected {total_len})"
            )

        # Parse TLV records
        points_xyz: np.ndarray | None = None
        points_dop: np.ndarray | None = None
        side_snr: np.ndarray | None = None

        offset = HEADER_SIZE
        for _ in range(num_tlvs):
            if offset + TLV_HEADER_SIZE > len(raw_data):
                break
            tlv_type, tlv_len = struct.unpack_from('<II', raw_data, offset)
            offset += TLV_HEADER_SIZE

            if offset + tlv_len > len(raw_data):
                break

            if tlv_type == TLV_TYPE_DETECTED_POINTS and tlv_len >= POINT_STRUCT_SIZE:
                n = tlv_len // POINT_STRUCT_SIZE
                vals = struct.unpack_from(f'<{n * 4}f', raw_data, offset)
                arr = np.array(vals, dtype=np.float32).reshape(n, 4)
                points_xyz = arr[:, :3]
                points_dop = arr[:, 3]

            elif tlv_type == TLV_TYPE_SIDE_INFO and tlv_len >= SIDE_INFO_STRUCT_SIZE:
                n = tlv_len // SIDE_INFO_STRUCT_SIZE
                vals = struct.unpack_from(f'<{n * 2}h', raw_data, offset)
                arr = np.array(vals, dtype=np.int16).reshape(n, 2)
                side_snr = arr[:, 0]  # SNR (0.1 dB units)

            offset += tlv_len

        if points_xyz is None or len(points_xyz) == 0:
            raise ParseError("検出物体なし (TLV Type 1 が存在しないか空)")

        mode = coordinate_mode or self._default_coordinate_mode
        n = len(points_xyz)

        x = points_xyz[:, 0]
        y = points_xyz[:, 1]
        z = points_xyz[:, 2]

        # Doppler velocity, ego-velocity compensated
        if points_dop is not None:
            velocity = (points_dop - self.velocity_offset).astype(np.float32)
        else:
            velocity = np.full(n, np.nan, dtype=np.float32)

        # Intensity from SNR (normalized to [0, 1])
        if side_snr is not None and len(side_snr) == n:
            # SNR in 0.1 dB units; 0–100 dB range → [0, 1]
            intensity = np.clip(side_snr.astype(np.float32) / 1000.0, 0.0, 1.0)
        else:
            intensity = np.ones(n, dtype=np.float32)

        points = self._build_points(x, y, z, velocity, intensity, n, mode)
        fields, types = self._build_schema(mode)

        host_ns = float(time.time_ns())
        timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        frame_id = self._next_frame_id()

        metadata = CepfMetadata(
            timestamp_utc=timestamp_utc,
            frame_id=frame_id,
            coordinate_system="sensor_local",
            coordinate_mode=mode.value,
            units={
                "position": "meters",
                "velocity": "m/s",
                "angle": "degrees",
                "intensity": "normalized",
            },
            sensor={
                "type": self.config.sensor_type.name.lower(),
                "model": self.config.model,
                "serial": self.config.serial_number or None,
                "firmware": self.config.firmware_version or None,
            },
        )

        extensions = {
            "radar": {
                "frame_number": int(frame_num),
                "num_detected_objects": n,
                "platform": int(platform),
                "subframe_number": int(subframe_num),
            }
        }

        return CepfFrame(
            format="CEPF",
            version="1.4.0",
            metadata=metadata,
            schema={"fields": fields, "types": types},
            points=points,
            point_count=n,
            extensions=extensions,
        )

    def _build_points(self, x, y, z, velocity, intensity, n, mode) -> CepfPoints:
        points: CepfPoints = {}

        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            points["x"] = x.astype(np.float32)
            points["y"] = y.astype(np.float32)
            points["z"] = z.astype(np.float32)

        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            dist = np.sqrt(x**2 + y**2 + z**2).astype(np.float32)
            if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
                az = np.rad2deg(np.arctan2(y, x)).astype(np.float32)
                horiz = np.sqrt(x**2 + y**2)
                el = np.rad2deg(np.arctan2(z, horiz)).astype(np.float32)
                points["azimuth"] = az
                points["elevation"] = el
            points["range"] = dist

        host_ns = float(time.time_ns())
        points["timestamp"] = np.full(n, host_ns, dtype=np.float64)
        points["intensity"] = intensity.astype(np.float32)
        points["velocity"] = velocity
        points["confidence"] = np.ones(n, dtype=np.float32)
        points["return_id"] = np.zeros(n, dtype=np.uint8)
        points["flags"] = np.full(n, int(PointFlag.VALID), dtype=np.uint16)

        return points

    def _build_schema(self, mode) -> tuple[list, list]:
        fields: list[str] = []
        types: list[str] = []
        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            fields.extend(["x", "y", "z"])
            types.extend(["f32", "f32", "f32"])
        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
            fields.extend(["azimuth", "elevation", "range"])
            types.extend(["f32", "f32", "f32"])
        if mode == CoordinateMode.CARTESIAN_WITH_RANGE:
            fields.append("range")
            types.append("f32")
        fields.extend(["timestamp", "intensity", "velocity", "confidence", "return_id", "flags"])
        types.extend(["f64", "f32", "f32", "f32", "u8", "u16"])
        return fields, types
