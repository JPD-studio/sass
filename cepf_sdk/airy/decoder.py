# cepf_sdk/airy/decoder.py
"""
後方互換ラッパー: UdpAiryDecoder / AiryDecodeConfig

既存の apps/run_pipeline.py が
  from cepf_sdk.airy import UdpAiryDecoder, AiryDecodeConfig
をインポートしているため残す。
内部実装は parsers/robosense_airy.py + drivers/robosense_airy_driver.py に委譲する。
"""
from __future__ import annotations

import socket
import time
import warnings
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from cepf_sdk.config import SensorConfig
from cepf_sdk.drivers.robosense_airy_driver import AiryDriverConfig, PKT_LEN
from cepf_sdk.enums import CoordinateMode, SensorType
from cepf_sdk.frame import CepfFrame
from cepf_sdk.parsers.robosense_airy import RoboSenseAiryParser


@dataclass
class AiryDecodeConfig:
    """後方互換用デコーダ設定"""
    bind_address: str = "0.0.0.0"
    port: int = 6699
    agg_seconds: float = 0.1
    coordinate_mode: str = "cartesian"
    num_channels: int = 96
    max_range_m: float = 200.0
    model: str = "RoboSense Airy"


class UdpAiryDecoder:
    """
    後方互換: UDP 受信 + パーサーで CepfFrame を生成する。

    新規コードでは以下を推奨:
        usc = UnifiedSenseCloud()
        usc.add_sensor("lidar_1", "robosense_airy", config)
    """

    def __init__(self, config: AiryDecodeConfig | None = None):
        warnings.warn(
            "UdpAiryDecoder is deprecated. Use UnifiedSenseCloud + RoboSenseAiryParser instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._config = config or AiryDecodeConfig()
        sensor_config = SensorConfig(
            sensor_type=SensorType.LIDAR,
            model=self._config.model,
            num_channels=self._config.num_channels,
            max_range_m=self._config.max_range_m,
        )
        self._parser = RoboSenseAiryParser(config=sensor_config)

        # coordinate_mode 文字列 → enum
        try:
            self._coord_mode = CoordinateMode(self._config.coordinate_mode)
        except ValueError:
            self._coord_mode = CoordinateMode.CARTESIAN

    def frames(self) -> Iterator[CepfFrame]:
        """
        UDP パケットを受信し、agg_seconds 秒分集約して CepfFrame を yield する。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._config.bind_address, self._config.port))
        sock.settimeout(5.0)

        frames_buf = []
        window_start = time.monotonic()

        try:
            while True:
                try:
                    data, _addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue

                if len(data) != PKT_LEN:
                    continue

                if not self._parser.validate(data):
                    continue

                try:
                    frame = self._parser.parse(data, coordinate_mode=self._coord_mode)
                    frames_buf.append(frame)
                except Exception:
                    continue

                now = time.monotonic()
                if now - window_start >= self._config.agg_seconds and frames_buf:
                    # 集約: 全パケットの points を結合して 1 フレームにまとめる
                    yield self._merge_frames(frames_buf)
                    frames_buf.clear()
                    window_start = now
        finally:
            sock.close()

    def _merge_frames(self, frames: list[CepfFrame]) -> CepfFrame:
        """複数パケットフレームをマージ"""
        from dataclasses import replace

        if len(frames) == 1:
            return frames[0]

        all_keys = set()
        for f in frames:
            all_keys.update(f.points.keys())

        merged = {}
        for key in all_keys:
            arrays = []
            for f in frames:
                arr = f.points.get(key)
                if arr is not None:
                    arrays.append(np.asarray(arr))
            if arrays:
                merged[key] = np.concatenate(arrays)

        total = sum(f.point_count for f in frames)
        base = frames[0]
        return replace(base, points=merged, point_count=total)
