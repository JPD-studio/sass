# cepf_sdk/parsers/robosense_airy.py
"""
RoboSense Airy パーサー。
ドライバー層 (drivers/robosense_airy_driver.py) の出力を CepfFrame に変換する。
"""
from __future__ import annotations

import time

import numpy as np

from cepf_sdk.config import SensorConfig
from cepf_sdk.drivers.robosense_airy_driver import (
    AiryDriverConfig,
    AiryPacketData,
    decode_packet,
    validate_packet,
)
from cepf_sdk.enums import CoordinateMode, PointFlag
from cepf_sdk.errors import ParseError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints


class RoboSenseAiryParser(RawDataParser):
    """
    RoboSense Airy パーサー。

    Ouster パーサーとの対比:
    - Ouster: ouster-sdk (外部) → parse_scan(LidarScan) → CepfFrame
    - Airy:   drivers/ (自前)   → parse(bytes) → CepfFrame
    """

    def __init__(self, config: SensorConfig,
                 driver_config: AiryDriverConfig | None = None):
        super().__init__(config)
        self._driver_config = driver_config or AiryDriverConfig()
        # 座標変換用 cos/sin テーブルを事前計算
        vert_deg = np.asarray(self._driver_config.vert_deg, dtype=np.float32)
        vert_rad = np.deg2rad(vert_deg)
        self._cos_vert = np.cos(vert_rad).astype(np.float32)
        self._sin_vert = np.sin(vert_rad).astype(np.float32)

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        1 パケット (1248 bytes) をパースして CepfFrame を返す。
        内部で drivers/robosense_airy_driver.decode_packet() を呼ぶ。
        """
        pkt_data = decode_packet(raw_data, self._driver_config)
        if pkt_data is None:
            raise ParseError("無効な Airy パケット")

        mode = coordinate_mode or self._default_coordinate_mode
        points = self._convert_to_points(pkt_data, mode)

        n = len(pkt_data.azimuth_deg)
        frame_id = self._next_frame_id()
        timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # schema を coordinate_mode に応じて構築
        fields = []
        types = []
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
            "lidar": {
                "channel_id": pkt_data.ring.astype(np.int32),
            },
            "airy": {
                "dist_word_u16": pkt_data.dist_word_u16,
                "dist_raw_u16": pkt_data.dist_raw_u16,
            },
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

    def _convert_to_points(self, pkt: AiryPacketData,
                           mode: CoordinateMode) -> CepfPoints:
        """AiryPacketData → 座標変換 → CepfPoints"""
        n = len(pkt.azimuth_deg)

        # 強度正規化
        intensity = np.clip(
            pkt.intensity_raw.astype(np.float32) / self._driver_config.intensity_div,
            0.0, 1.0
        )

        # タイムスタンプ: ホスト時刻ベース
        host_ns = int(time.time_ns())
        timestamp = np.full(n, float(host_ns), dtype=np.float64)

        velocity = np.full(n, np.nan, dtype=np.float32)
        confidence = np.ones(n, dtype=np.float32)
        return_id = np.zeros(n, dtype=np.uint8)
        flags = np.full(n, PointFlag.VALID, dtype=np.uint16)

        points: CepfPoints = {}

        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            az_rad = np.deg2rad(pkt.azimuth_deg)
            el_rad = np.deg2rad(pkt.elevation_deg)
            cos_el = np.cos(el_rad)
            points["x"] = (pkt.distance_m * cos_el * np.cos(az_rad)).astype(np.float32)
            points["y"] = (pkt.distance_m * cos_el * np.sin(az_rad)).astype(np.float32)
            points["z"] = (pkt.distance_m * np.sin(el_rad)).astype(np.float32)

        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
            points["azimuth"] = pkt.azimuth_deg.copy()
            points["elevation"] = pkt.elevation_deg.copy()
            points["range"] = pkt.distance_m.copy()

        if mode == CoordinateMode.CARTESIAN_WITH_RANGE:
            points["range"] = pkt.distance_m.copy()

        points["timestamp"] = timestamp
        points["intensity"] = intensity
        points["velocity"] = velocity
        points["confidence"] = confidence
        points["return_id"] = return_id
        points["flags"] = flags

        return points

    def validate(self, raw_data: bytes) -> bool:
        """パケットの妥当性を検証"""
        return validate_packet(raw_data)
