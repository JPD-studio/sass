# cepf_sdk/parsers/ouster.py
"""
Ouster LiDAR 共通パーサー基底クラス。
ouster-sdk (pip install ouster-sdk) を内部依存として使用する。

インストール:
    pip install cepf-sdk[ouster]
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import numpy as np

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, PointFlag, SensorType
from cepf_sdk.errors import ConfigurationError, ParseError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints

# --- ouster-sdk の遅延インポート（optional dependency） ---
try:
    from ouster.sdk import open_source
    from ouster.sdk.core import SensorInfo, XYZLut
    _HAS_OUSTER = True
except ImportError:
    _HAS_OUSTER = False


def _require_ouster() -> None:
    """ouster-sdk が未インストールの場合に明確なエラーを出す。"""
    if not _HAS_OUSTER:
        raise ImportError(
            "ouster-sdk が必要です。以下のコマンドでインストールしてください:\n"
            "  pip install cepf-sdk[ouster]\n"
            "または:\n"
            "  pip install ouster-sdk"
        )


@dataclass
class OusterConfig:
    """Ouster センサ固有の設定。SensorConfig と併用。"""
    source_url: str = ""
    """ライブセンサのホスト名、または PCAP ファイルパス"""
    meta_json: str = ""
    """PCAP 再生時のメタデータ JSON ファイルパス（ライブ時は空）"""
    collate: bool = True
    """PCAP 再生時の collate オプション"""


class OusterBaseParser(RawDataParser):
    """
    Ouster LiDAR 共通パーサー。
    ouster-sdk の LidarScan を受け取り CepfFrame に変換する。

    通常の RawDataParser.parse(bytes) とは異なり、
    parse_scan(scan) メソッドで LidarScan を直接受け渡す。
    """

    def __init__(self, config: SensorConfig,
                 ouster_config: OusterConfig | None = None):
        _require_ouster()
        super().__init__(config)
        self._ouster_config = ouster_config or OusterConfig()
        self._sensor_info: Any = None
        self._xyz_lut: Any = None

    def set_sensor_info(self, info: Any) -> None:
        """SensorInfo を設定し、XYZLut を初期化する。"""
        self._sensor_info = info
        self._xyz_lut = XYZLut(info)

    @property
    def sensor_info(self) -> Any:
        return self._sensor_info

    @property
    def model_name(self) -> str:
        """センサモデル名"""
        if self._sensor_info:
            return self._sensor_info.prod_line
        return self.config.model

    @property
    def columns_per_frame(self) -> int:
        """1 フレームあたりの列数"""
        if self._sensor_info:
            return self._sensor_info.format.columns_per_frame
        return 0

    @property
    def pixels_per_column(self) -> int:
        """1 列あたりのピクセル数（= チャンネル数）"""
        if self._sensor_info:
            return self._sensor_info.format.pixels_per_column
        return 0

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        bytes インターフェース（基底クラスの互換性のため）。
        Ouster では通常 parse_scan() を使用する。
        """
        raise NotImplementedError(
            "Ouster パーサーは parse_scan(scan) を使用してください。"
            "ouster-sdk の open_source() で取得した LidarScan を渡してください。"
        )

    def parse_scan(self, scan: Any,
                   coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        ouster.sdk.client.LidarScan を CepfFrame に変換する。

        Parameters
        ----------
        scan : ouster.sdk.client.LidarScan
            1 フレーム分の LiDAR スキャンデータ
        coordinate_mode : CoordinateMode | None
            座標モード。None の場合はデフォルト値を使用
        """
        if self._xyz_lut is None:
            raise ConfigurationError(
                "SensorInfo が未設定です。set_sensor_info() を先に呼んでください。"
            )

        mode = coordinate_mode or self._default_coordinate_mode

        # ---- XYZ 座標の取得 ----
        xyz = self._xyz_lut(scan)               # (H, W, 3) ndarray
        xyz_flat = xyz.reshape(-1, 3)            # (N, 3)
        x = xyz_flat[:, 0].astype(np.float32)
        y = xyz_flat[:, 1].astype(np.float32)
        z = xyz_flat[:, 2].astype(np.float32)

        # ---- 距離 ----
        range_field = scan.field(self._range_field_id())
        range_m = range_field.reshape(-1).astype(np.float32) * 0.001  # mm → m

        # ---- 強度（反射率） ----
        reflectivity = scan.field(self._reflectivity_field_id())
        intensity = reflectivity.reshape(-1).astype(np.float32) / 65535.0

        # ---- 信号強度とノイズ → 信頼度 ----
        signal_arr = self._safe_field(scan, self._signal_field_id())
        noise_arr = self._safe_field(scan, self._near_ir_field_id())

        if signal_arr is not None and noise_arr is not None:
            sig = signal_arr.reshape(-1).astype(np.float32)
            noi = noise_arr.reshape(-1).astype(np.float32)
            confidence = np.clip(sig / np.maximum(noi, 1.0) / 100.0, 0.0, 1.0)
        else:
            confidence = np.ones_like(x)

        n = len(x)

        # ---- タイムスタンプ ----
        host_ns = int(time.time_ns())
        timestamp = np.full(n, float(host_ns), dtype=np.float64)

        # ---- CepfPoints の構築 ----
        points: CepfPoints = {}
        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            points["x"] = x
            points["y"] = y
            points["z"] = z
        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
            points["azimuth"] = np.degrees(np.arctan2(y, x)).astype(np.float32)
            points["elevation"] = np.degrees(np.arctan2(
                z, np.sqrt(x**2 + y**2)
            )).astype(np.float32)
            points["range"] = range_m
        if mode == CoordinateMode.CARTESIAN_WITH_RANGE:
            points["range"] = range_m

        points["timestamp"] = timestamp
        points["intensity"] = intensity
        points["velocity"] = np.full(n, np.nan, dtype=np.float32)
        points["confidence"] = confidence
        points["return_id"] = np.zeros(n, dtype=np.uint8)
        points["flags"] = np.full(n, PointFlag.VALID, dtype=np.uint16)

        # ---- schema ----
        fields = list(points.keys())
        type_map = {
            "x": "f32", "y": "f32", "z": "f32",
            "azimuth": "f32", "elevation": "f32", "range": "f32",
            "timestamp": "f64", "intensity": "f32", "velocity": "f32",
            "confidence": "f32", "return_id": "u8", "flags": "u16",
        }
        types = [type_map.get(f, "f32") for f in fields]

        # ---- メタデータ ----
        frame_id = self._next_frame_id()
        metadata = CepfMetadata(
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
                "type": "lidar",
                "model": self.model_name,
            },
        )

        return CepfFrame(
            format="CEPF",
            version="1.4.0",
            metadata=metadata,
            schema={"fields": fields, "types": types},
            points=points,
            point_count=n,
        )

    # --- フィールド ID ヘルパー ---
    # ouster-sdk v0.16+ では ChanField は文字列定数 (ouster.sdk.core)
    # 旧 v0.13 では整数 (ouster.sdk.client)

    @staticmethod
    def _get_chanfield():
        try:
            from ouster.sdk.core import ChanField
            return ChanField
        except ImportError:
            try:
                from ouster.sdk.client import ChanField
                return ChanField
            except ImportError:
                return None

    def _range_field_id(self):
        cf = self._get_chanfield()
        return cf.RANGE if cf is not None else "RANGE"

    def _reflectivity_field_id(self):
        cf = self._get_chanfield()
        return cf.REFLECTIVITY if cf is not None else "REFLECTIVITY"

    def _signal_field_id(self):
        cf = self._get_chanfield()
        return cf.SIGNAL if cf is not None else "SIGNAL"

    def _near_ir_field_id(self):
        cf = self._get_chanfield()
        return cf.NEAR_IR if cf is not None else "NEAR_IR"

    def _safe_field(self, scan: Any, field_id: int) -> Optional[np.ndarray]:
        """フィールドが存在しない場合は None を返す。"""
        try:
            return scan.field(field_id)
        except (ValueError, KeyError):
            return None

    def validate(self, raw_data: bytes) -> bool:
        """Ouster では ouster-sdk がバリデーションを行うため常に True。"""
        return True

    def open_source_iter(self) -> Iterator[Any]:
        """
        OusterConfig の設定に基づき ouster.sdk.open_source() を開き、
        LidarScan のイテレータを返す。
        """
        _require_ouster()
        cfg = self._ouster_config
        if cfg.meta_json:
            src = open_source(cfg.source_url, meta=[cfg.meta_json],
                              collate=cfg.collate)
        else:
            src = open_source(cfg.source_url)

        if hasattr(src, 'sensor_info') and src.sensor_info:
            info = src.sensor_info[0] if isinstance(src.sensor_info, list) else src.sensor_info
            self.set_sensor_info(info)

        return src


class OusterLidarParser(OusterBaseParser):
    """
    Ouster OS0/OS1/OS2 シリーズ汎用パーサー。
    prod_line 情報は ouster-sdk の SensorInfo から自動取得される。
    """

    def __init__(self, config: SensorConfig | None = None,
                 ouster_config: OusterConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.LIDAR,
                model="Ouster OS",
                num_channels=128,
                horizontal_fov_deg=360.0,
                vertical_fov_deg=45.0,
                max_range_m=240.0,
            )
        super().__init__(config, ouster_config)
