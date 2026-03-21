# cepf_sdk/config.py
"""CEPF SDK 設定クラス"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cepf_sdk.enums import SensorType


@dataclass
class SensorConfig:
    """センサー構成情報"""
    sensor_type: SensorType
    model: str
    serial_number: str = ""
    firmware_version: str = ""
    num_channels: int = 0
    horizontal_fov_deg: float = 360.0
    vertical_fov_deg: float = 45.0
    max_range_m: float = 200.0
    range_resolution_m: float = 0.1
    velocity_resolution_mps: float = 0.1
    axis_sign: dict = field(default_factory=lambda: {"x": 1, "y": 1, "z": 1})
    """軸符号変換設定。x/y/z それぞれ 1 (正方向維持) または -1 (符号反転)。"""


@dataclass
class Transform:
    """座標変換パラメータ"""
    translation: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64)
    )
    rotation_quaternion: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    )

    def to_matrix(self) -> np.ndarray:
        """4x4 同次変換行列を返す"""
        from cepf_sdk.utils.quaternion import quaternion_to_rotation_matrix
        R = quaternion_to_rotation_matrix(self.rotation_quaternion)
        M = np.eye(4, dtype=np.float64)
        M[:3, :3] = R
        M[:3, 3] = self.translation
        return M

    @classmethod
    def from_matrix(cls, m: np.ndarray) -> Transform:
        """4x4 同次変換行列からインスタンスを生成"""
        from cepf_sdk.utils.quaternion import rotation_matrix_to_quaternion
        translation = m[:3, 3].copy()
        q = rotation_matrix_to_quaternion(m[:3, :3])
        return cls(translation=translation, rotation_quaternion=q)

    def inverse(self) -> Transform:
        """逆変換を返す"""
        M = self.to_matrix()
        M_inv = np.linalg.inv(M)
        return Transform.from_matrix(M_inv)


@dataclass
class InstallationInfo:
    """設置情報 (v1.1追加)"""
    reference_description: str = ""
    reference_latitude: float = 0.0
    reference_longitude: float = 0.0
    reference_altitude: float = 0.0
    reference_datum: str = "WGS84"
    sensor_offset: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64)
    )
    sensor_offset_description: str = ""
