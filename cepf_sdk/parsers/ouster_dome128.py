# cepf_sdk/parsers/ouster_dome128.py
"""Ouster Dome 128 用パーサー。"""
from __future__ import annotations

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import SensorType
from cepf_sdk.parsers.ouster import OusterBaseParser, OusterConfig


class OusterDome128Parser(OusterBaseParser):
    """
    Ouster Dome 128 半天球 LiDAR パーサー。

    Dome 128 固有の特徴:
    - 128ch × 1024/2048 列
    - 半天球 FoV（上方 90°）
    - Dome 専用のビームパターン
    """

    def __init__(self, config: SensorConfig | None = None,
                 ouster_config: OusterConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.LIDAR,
                model="Ouster Dome 128",
                num_channels=128,
                horizontal_fov_deg=360.0,
                vertical_fov_deg=90.0,
                max_range_m=100.0,
            )
        super().__init__(config, ouster_config)
