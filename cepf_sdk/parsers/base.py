# cepf_sdk/parsers/base.py
"""RawDataParser 抽象基底クラス"""
from __future__ import annotations

from abc import ABC, abstractmethod

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode
from cepf_sdk.frame import CepfFrame


class RawDataParser(ABC):
    """RAW データパーサーの基底クラス。全パーサーはこれを継承する。"""

    def __init__(self, config: SensorConfig):
        self.config = config
        self._frame_id_counter = 0
        self._default_coordinate_mode = CoordinateMode.CARTESIAN

    def _next_frame_id(self) -> int:
        """フレームID連番を発行"""
        self._frame_id_counter += 1
        return self._frame_id_counter

    def set_default_coordinate_mode(self, mode: CoordinateMode) -> RawDataParser:
        """デフォルト座標表現形式を設定"""
        self._default_coordinate_mode = mode
        return self

    @abstractmethod
    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """RAW データをパースして CepfFrame を返す。"""
        ...

    @abstractmethod
    def validate(self, raw_data: bytes) -> bool:
        """データの妥当性を検証する。"""
        ...
