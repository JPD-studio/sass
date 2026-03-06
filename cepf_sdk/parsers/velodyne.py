# cepf_sdk/parsers/velodyne.py
"""Velodyne VLP/HDL シリーズ用パーサー"""
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

PACKET_SIZE = 1206
BLOCKS_PER_PACKET = 12
CHANNELS_PER_BLOCK = 32
BLOCK_SIZE = 100  # 2 (flag) + 2 (azimuth) + 32*3 (channels)
BLOCK_FLAG = 0xFFEE

# VLP-16: 16 channels, 2 firings per block (elevation angles in degrees)
VERT_ANGLES_VLP16 = np.array([
    -15.0, 1.0, -13.0, 3.0, -11.0, 5.0, -9.0, 7.0,
    -7.0, 9.0, -5.0, 11.0, -3.0, 13.0, -1.0, 15.0,
], dtype=np.float32)

# VLP-32C / HDL-32E: 32 channels, 1 firing per block
VERT_ANGLES_VLP32 = np.array([
    -25.0, -1.0, -1.667, -15.639, -11.31, 0.0, -0.667, -8.843,
    -7.254, 0.333, -0.333, -6.148, -5.333, 1.333, 0.667, -4.0,
    -4.667, 1.667, 1.0, -3.667, -3.333, 3.333, 2.333, -2.667,
    -3.0, 7.0, 4.667, -2.333, -2.0, 15.0, 10.333, -1.333,
], dtype=np.float32)


class VelodyneLidarParser(RawDataParser):
    """
    Velodyne VLP-16/32C, HDL-32E 用パーサー。

    num_channels <= 16: VLP-16 モード (2 firings per block)
    num_channels == 32: VLP-32C / HDL-32E モード (1 firing per block)
    """

    def __init__(self, config: SensorConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.LIDAR,
                model="Velodyne VLP-16",
                num_channels=16,
                horizontal_fov_deg=360.0,
                vertical_fov_deg=30.0,
                max_range_m=100.0,
            )
        super().__init__(config)
        n_ch = self.config.num_channels or 16
        if n_ch <= 16:
            self._vert_angles = VERT_ANGLES_VLP16
            self._firings_per_block = 2  # VLP-16: 2 firings of 16 channels
        else:
            self._vert_angles = VERT_ANGLES_VLP32
            self._firings_per_block = 1  # VLP-32C: 1 firing of 32 channels

    def validate(self, raw_data: bytes) -> bool:
        return len(raw_data) == PACKET_SIZE

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        if not self.validate(raw_data):
            raise ParseError(
                f"無効な Velodyne パケット (size={len(raw_data)}, expected={PACKET_SIZE})"
            )

        mode = coordinate_mode or self._default_coordinate_mode
        az, el, dist, intensity, ring = self._decode_packet(raw_data)

        if len(dist) == 0:
            raise ParseError("有効な点が含まれていません (全距離ゼロ)")

        n = len(dist)
        points = self._build_points(az, el, dist, intensity, n, mode)
        fields, types = self._build_schema(mode)

        frame_id = self._next_frame_id()
        timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        metadata = CepfMetadata(
            timestamp_utc=timestamp_utc,
            frame_id=frame_id,
            coordinate_system="sensor_local",
            coordinate_mode=mode.value,
            units={
                "position": "meters",
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

        return CepfFrame(
            format="CEPF",
            version="1.4.0",
            metadata=metadata,
            schema={"fields": fields, "types": types},
            points=points,
            point_count=n,
            extensions={"lidar": {"channel_id": ring.astype(np.int32)}},
        )

    def _decode_packet(self, raw_data: bytes):
        """1206バイトパケットをデコードし (az, el, dist, intensity, ring) を返す。"""
        block_az = np.zeros(BLOCKS_PER_PACKET, dtype=np.float32)
        block_dist = np.zeros((BLOCKS_PER_PACKET, CHANNELS_PER_BLOCK), dtype=np.float32)
        block_inten = np.zeros((BLOCKS_PER_PACKET, CHANNELS_PER_BLOCK), dtype=np.float32)

        for bi in range(BLOCKS_PER_PACKET):
            base = bi * BLOCK_SIZE
            flag = struct.unpack_from('<H', raw_data, base)[0]
            if flag != BLOCK_FLAG:
                continue
            az_raw = struct.unpack_from('<H', raw_data, base + 2)[0]
            block_az[bi] = az_raw / 100.0
            for ci in range(CHANNELS_PER_BLOCK):
                ch_base = base + 4 + ci * 3
                d_raw = struct.unpack_from('<H', raw_data, ch_base)[0]
                block_dist[bi, ci] = d_raw * 0.002
                block_inten[bi, ci] = raw_data[ch_base + 2] / 255.0

        if self._firings_per_block == 2:
            return self._unpack_vlp16(block_az, block_dist, block_inten)
        else:
            return self._unpack_vlp32(block_az, block_dist, block_inten)

    def _unpack_vlp16(self, block_az, block_dist, block_inten):
        """VLP-16: channels 0-15 = 1st firing, 16-31 = 2nd firing。"""
        # 2nd firing azimuth: interpolated between current and next block
        diff = np.diff(block_az)
        diff[diff < 0] += 360.0  # wraparound
        az2 = block_az.copy()
        az2[:-1] += diff / 2.0

        n_ch = len(self._vert_angles)  # 16

        f1_az = np.repeat(block_az, n_ch)
        f1_el = np.tile(self._vert_angles, BLOCKS_PER_PACKET)
        f1_dist = block_dist[:, :n_ch].reshape(-1)
        f1_inten = block_inten[:, :n_ch].reshape(-1)
        f1_ring = np.tile(np.arange(n_ch, dtype=np.uint8), BLOCKS_PER_PACKET)

        f2_az = np.repeat(az2, n_ch)
        f2_el = np.tile(self._vert_angles, BLOCKS_PER_PACKET)
        f2_dist = block_dist[:, n_ch:].reshape(-1)
        f2_inten = block_inten[:, n_ch:].reshape(-1)
        f2_ring = np.tile(np.arange(n_ch, dtype=np.uint8), BLOCKS_PER_PACKET)

        az = np.concatenate([f1_az, f2_az])
        el = np.concatenate([f1_el, f2_el])
        dist = np.concatenate([f1_dist, f2_dist])
        inten = np.concatenate([f1_inten, f2_inten])
        ring = np.concatenate([f1_ring, f2_ring])

        valid = dist > 0.0
        return az[valid], el[valid], dist[valid], inten[valid], ring[valid]

    def _unpack_vlp32(self, block_az, block_dist, block_inten):
        """VLP-32C / HDL-32E: 1 firing per block, 32 channels。"""
        n_ch = len(self._vert_angles)  # 32
        az = np.repeat(block_az, n_ch)
        el = np.tile(self._vert_angles, BLOCKS_PER_PACKET)
        dist = block_dist.reshape(-1)
        inten = block_inten.reshape(-1)
        ring = np.tile(np.arange(n_ch, dtype=np.uint8), BLOCKS_PER_PACKET)

        valid = dist > 0.0
        return az[valid], el[valid], dist[valid], inten[valid], ring[valid]

    def _build_points(self, az, el, dist, intensity, n, mode) -> CepfPoints:
        """球面座標 → CepfPoints 変換"""
        host_ns = float(time.time_ns())
        points: CepfPoints = {}

        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            az_rad = np.deg2rad(az)
            el_rad = np.deg2rad(el)
            cos_el = np.cos(el_rad)
            points["x"] = (dist * cos_el * np.cos(az_rad)).astype(np.float32)
            points["y"] = (dist * cos_el * np.sin(az_rad)).astype(np.float32)
            points["z"] = (dist * np.sin(el_rad)).astype(np.float32)

        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
            points["azimuth"] = az.astype(np.float32)
            points["elevation"] = el.astype(np.float32)
            points["range"] = dist.astype(np.float32)

        if mode == CoordinateMode.CARTESIAN_WITH_RANGE:
            points["range"] = dist.astype(np.float32)

        points["timestamp"] = np.full(n, host_ns, dtype=np.float64)
        points["intensity"] = intensity.astype(np.float32)
        points["velocity"] = np.full(n, np.nan, dtype=np.float32)
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
