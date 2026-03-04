# cepf_sdk/usc.py
"""UnifiedSenseCloud — マルチセンサ統合ファクトリークラス"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from cepf_sdk.config import InstallationInfo, SensorConfig, Transform
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, SensorType
from cepf_sdk.errors import (
    ParserNotFoundError,
    SensorNotFoundError,
    ValidationError,
)
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints

logger = logging.getLogger(__name__)


class UnifiedSenseCloud:
    """
    LiDAR/Radar RAWデータをCEPF形式に変換する統合ファクトリークラス。

    使い方:
        usc = UnifiedSenseCloud()
        usc.add_sensor("lidar_1", "robosense_airy", config)
        frame = usc.forge("lidar_1", raw_bytes)
    """

    # クラス属性: カスタムパーサー登録（遅延インポートマップに追加）
    _custom_parsers: Dict[str, type] = {}

    def __init__(self) -> None:
        self._parsers: Dict[str, RawDataParser] = {}
        self._transform = Transform()
        self._filters: List[Callable[[CepfFrame], CepfFrame]] = []
        self._output_coordinate = CoordinateSystem.SENSOR_LOCAL
        self._output_coordinate_mode = CoordinateMode.CARTESIAN
        self._installation: Optional[InstallationInfo] = None

    @classmethod
    def register_parser(cls, name: str, parser_class: type) -> None:
        """カスタムパーサーをクラスレベルで登録"""
        cls._custom_parsers[name] = parser_class

    @classmethod
    def from_json(cls, config_path: str) -> UnifiedSenseCloud:
        """
        JSON 設定ファイルから USC インスタンスを生成する。

        Parameters
        ----------
        config_path : str
            JSON ファイルパス
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)

        usc = cls()

        # センサー設定を読み込み
        for sensor_cfg in config_dict.get('sensors', []):
            sensor_config_dict = sensor_cfg.get('config', {})

            # sensor_type を文字列 → enum に変換
            st = sensor_config_dict.get('sensor_type', 'UNKNOWN')
            if isinstance(st, str):
                sensor_config_dict['sensor_type'] = SensorType[st.upper()]

            sensor_config = SensorConfig(**sensor_config_dict)
            usc.add_sensor(
                sensor_id=sensor_cfg['sensor_id'],
                parser_name=sensor_cfg['parser_name'],
                config=sensor_config,
            )

            # Transform 設定（存在すれば）
            if 'transform' in sensor_cfg:
                t = sensor_cfg['transform']
                usc.set_transform(
                    translation=t.get('translation', [0, 0, 0]),
                    rotation_quat=t.get('rotation_quaternion', [1, 0, 0, 0]),
                )

        # Installation 設定（存在すれば）
        if 'installation' in config_dict:
            inst_dict = config_dict['installation']
            # sensor_offset を ndarray に変換
            if 'sensor_offset' in inst_dict:
                inst_dict['sensor_offset'] = np.array(
                    inst_dict['sensor_offset'], dtype=np.float64
                )
            usc.set_installation(InstallationInfo(**inst_dict))

        return usc

    def add_sensor(self, sensor_id: str, parser_name: str,
                   config: SensorConfig, **kwargs: Any) -> UnifiedSenseCloud:
        """センサー追加"""
        # カスタム登録をまず確認
        if parser_name in self._custom_parsers:
            parser_cls = self._custom_parsers[parser_name]
        else:
            from cepf_sdk.parsers import get_parser_class
            parser_cls = get_parser_class(parser_name)

        # パーサー固有の追加引数（ouster_config等）を渡す
        parser = parser_cls(config=config, **kwargs)
        self._parsers[sensor_id] = parser
        logger.info("Sensor added: %s (parser=%s)", sensor_id, parser_name)
        return self

    def set_transform(self, translation: List[float],
                      rotation_quat: List[float]) -> UnifiedSenseCloud:
        """座標変換設定"""
        self._transform = Transform(
            translation=np.array(translation, dtype=np.float64),
            rotation_quaternion=np.array(rotation_quat, dtype=np.float64),
        )
        return self

    def set_output_coordinate(self, coord_sys: CoordinateSystem) -> UnifiedSenseCloud:
        """出力座標系設定"""
        self._output_coordinate = coord_sys
        return self

    def set_output_coordinate_mode(self, coord_mode: CoordinateMode) -> UnifiedSenseCloud:
        """出力座標表現形式設定"""
        self._output_coordinate_mode = coord_mode
        return self

    def set_installation(self, installation: InstallationInfo) -> UnifiedSenseCloud:
        """設置情報設定"""
        self._installation = installation
        return self

    def add_filter(self, filter_func: Callable[[CepfFrame], CepfFrame]) -> UnifiedSenseCloud:
        """フィルター追加"""
        self._filters.append(filter_func)
        return self

    def forge(self, sensor_id: str, raw_data: Any,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        単一センサー変換。

        Parameters
        ----------
        sensor_id : str
            add_sensor() で登録したセンサーID
        raw_data : bytes | Any
            RAW データ（Ouster の場合は LidarScan）
        coordinate_mode : CoordinateMode | None
            座標モード（None の場合はデフォルト）
        """
        # ① sensor_id → パーサーを特定
        parser = self._parsers.get(sensor_id)
        if parser is None:
            raise SensorNotFoundError(
                f"Sensor not found: {sensor_id!r}. "
                f"Registered: {list(self._parsers.keys())}"
            )

        # ② validate()
        if isinstance(raw_data, bytes):
            if not parser.validate(raw_data):
                raise ValidationError(f"Validation failed for sensor {sensor_id!r}")

        # ③ coordinate_mode の決定
        mode = coordinate_mode or self._output_coordinate_mode

        # ④ parse()
        if isinstance(raw_data, bytes):
            frame = parser.parse(raw_data, coordinate_mode=mode)
        else:
            # Ouster 等の LidarScan 対応
            if hasattr(parser, 'parse_scan'):
                frame = parser.parse_scan(raw_data, coordinate_mode=mode)
            else:
                frame = parser.parse(raw_data, coordinate_mode=mode)

        # ⑤ 設置情報付与
        if self._installation is not None:
            inst = self._installation
            installation_dict = {
                "reference_point": {
                    "description": inst.reference_description,
                    "latitude": inst.reference_latitude,
                    "longitude": inst.reference_longitude,
                    "altitude": inst.reference_altitude,
                    "datum": inst.reference_datum,
                },
                "sensor_offset_from_reference": {
                    "description": inst.sensor_offset_description,
                    "offset_x": float(inst.sensor_offset[0]),
                    "offset_y": float(inst.sensor_offset[1]),
                    "offset_z": float(inst.sensor_offset[2]),
                },
            }
            frame = replace(
                frame,
                metadata=replace(frame.metadata, installation=installation_dict),
            )

        # ⑥ 座標変換 Transform を適用（SENSOR_LOCAL 以外の場合）
        if self._output_coordinate != CoordinateSystem.SENSOR_LOCAL:
            frame = frame.transform_points(self._transform)
            frame = replace(
                frame,
                metadata=replace(
                    frame.metadata,
                    coordinate_system=self._output_coordinate.value,
                    transform_to_world={
                        "translation": self._transform.translation.tolist(),
                        "rotation_quaternion": self._transform.rotation_quaternion.tolist(),
                    },
                ),
            )

        # ⑦ フィルターを順次適用
        for filter_func in self._filters:
            frame = filter_func(frame)

        logger.info(
            "forge complete: sensor=%s points=%d",
            sensor_id, frame.point_count,
        )
        return frame

    def forge_multi(self, data_dict: Dict[str, Any],
                    coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        複数センサー統合変換。

        処理フロー:
        1. 空のCEPFFrame生成
        2. data_dict の各エントリに対し forge() 実行
        3. 全フレームの points をマージ
        4. extensions を統合（センサー種別ごと）
        5. 統合CEPFFrame返却

        Parameters
        ----------
        data_dict : dict[str, bytes | Any]
            sensor_id → RAW データのマッピング
        coordinate_mode : CoordinateMode | None
            座標モード（None の場合はデフォルト）

        Returns
        -------
        CepfFrame
            全センサーの点群をマージした統合フレーム
        """
        if not data_dict:
            raise ValueError("data_dict is empty")

        frames: List[CepfFrame] = []
        for sensor_id, raw_data in data_dict.items():
            frame = self.forge(sensor_id, raw_data, coordinate_mode=coordinate_mode)
            frames.append(frame)

        if len(frames) == 1:
            return frames[0]

        # --- 複数フレームの points をマージ ---
        all_keys: set[str] = set()
        for f in frames:
            all_keys.update(f.points.keys())

        merged_points: Dict[str, np.ndarray] = {}
        for key in all_keys:
            arrays: List[np.ndarray] = []
            for f in frames:
                arr = f.points.get(key)  # type: ignore[arg-type]
                if arr is not None:
                    arrays.append(np.asarray(arr))
                else:
                    # このフレームにはこのフィールドがない → NaN/0 で埋める
                    n = f.point_count
                    sample = next(
                        (np.asarray(v) for v in f.points.values()), None
                    )
                    if sample is not None and sample.dtype.kind == 'f':
                        arrays.append(np.full(n, np.nan, dtype=sample.dtype))
                    else:
                        arrays.append(np.zeros(n, dtype=np.float32))
            if arrays:
                merged_points[key] = np.concatenate(arrays)

        total_count = sum(f.point_count for f in frames)

        # --- extensions を統合（センサー種別ごと） ---
        merged_extensions: Dict[str, Any] = {}
        for f in frames:
            if f.extensions:
                for ext_key, ext_val in f.extensions.items():
                    if ext_key not in merged_extensions:
                        merged_extensions[ext_key] = ext_val
                    elif isinstance(ext_val, dict) and isinstance(
                        merged_extensions[ext_key], dict
                    ):
                        merged_extensions[ext_key].update(ext_val)

        # 基準フレーム（最初のフレーム）のメタデータをベースにする
        base = frames[0]

        # schema を統合（全フィールド）
        fields = list(merged_points.keys())
        type_map = {
            "x": "f32", "y": "f32", "z": "f32",
            "azimuth": "f32", "elevation": "f32", "range": "f32",
            "timestamp": "f64", "intensity": "f32", "velocity": "f32",
            "confidence": "f32", "return_id": "u8", "flags": "u16",
        }
        types = [type_map.get(f, "f32") for f in fields]

        merged_frame = CepfFrame(
            format="CEPF",
            version=base.version,
            metadata=base.metadata,
            schema={"fields": fields, "types": types},
            points=merged_points,
            point_count=total_count,
            extensions=merged_extensions or None,
        )

        logger.info(
            "forge_multi complete: sensors=%d total_points=%d",
            len(frames), total_count,
        )
        return merged_frame

    def get_parser(self, sensor_id: str) -> Optional[RawDataParser]:
        """
        登録済みパーサーを取得する。

        Parameters
        ----------
        sensor_id : str
            add_sensor() で登録したセンサーID

        Returns
        -------
        RawDataParser | None
            登録済みパーサー。未登録なら None。
        """
        return self._parsers.get(sensor_id)