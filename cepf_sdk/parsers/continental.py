# cepf_sdk/parsers/continental.py
"""Continental ARS シリーズ用パーサー（スケルトン実装）"""
from __future__ import annotations

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, SensorType
from cepf_sdk.frame import CepfFrame
from cepf_sdk.parsers.base import RawDataParser


class ContinentalRadarParser(RawDataParser):
    """
    Continental ARS408/ARS540 シリーズ用パーサー。
    将来実装予定。
    """

    def __init__(self, config: SensorConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.RADAR,
                model="Continental ARS408",
                max_range_m=250.0,
            )
        super().__init__(config)
        self.velocity_offset: float = 0.0

    def set_ego_velocity(self, velocity_mps: float) -> None:
        """自車速度設定"""
        self.velocity_offset = velocity_mps

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        raise NotImplementedError("Continental Radar parser is not yet implemented")

    def validate(self, raw_data: bytes) -> bool:
        return len(raw_data) > 0
