# tests/test_parsers/test_ouster.py
"""Ouster パーサーのテスト（ouster-sdk 未インストール環境でのガード含む）"""
from __future__ import annotations

import numpy as np
import pytest

# ouster-sdk が利用可能かどうかを判定
try:
    from ouster.sdk.core import (
        ChanField, LidarMode, LidarScan, SensorInfo, XYZLut,
    )
    _HAS_OUSTER = True
except ImportError:
    _HAS_OUSTER = False

# ouster-sdk が必要なテストは skip デコレータで制御
requires_ouster = pytest.mark.skipif(
    not _HAS_OUSTER, reason="ouster-sdk not installed"
)


# ---------------------------------------------------------------------------
# ヘルパー: モック LidarScan の生成
# ---------------------------------------------------------------------------

def _make_sensor_info() -> "SensorInfo":
    """テスト用の SensorInfo (OS-1-64, 1024x10 モード)"""
    return SensorInfo.from_default(LidarMode.MODE_1024x10)


def _make_scan(info: "SensorInfo") -> "LidarScan":
    """全フィールドに既知値を設定した LidarScan を返す。"""
    H = info.format.pixels_per_column
    W = info.format.columns_per_frame
    scan = LidarScan(H, W)

    # RANGE: 5000 mm = 5.0 m
    scan.field(ChanField.RANGE)[:] = np.full((H, W), 5000, dtype=np.uint32)
    # REFLECTIVITY: 最大値の半分
    scan.field(ChanField.REFLECTIVITY)[:] = np.full((H, W), 32767, dtype=np.uint16)
    # SIGNAL: 適度な信号強度
    scan.field(ChanField.SIGNAL)[:] = np.full((H, W), 1000, dtype=np.uint16)
    # NEAR_IR: 低ノイズ
    scan.field(ChanField.NEAR_IR)[:] = np.full((H, W), 10, dtype=np.uint16)
    return scan


# ---------------------------------------------------------------------------
# 既存テスト (import ガード)
# ---------------------------------------------------------------------------

class TestOusterImportGuard:
    """ouster-sdk が無い環境でもインポートエラーにならないことを確認"""

    def test_import_module(self):
        """parsers/__init__.py は遅延インポートなのでインポート自体は成功する"""
        from cepf_sdk.parsers import get_parser_class
        # ouster-sdk が無ければ、インスタンス化で ImportError が出る
        # ここではクラス取得のみテスト
        try:
            cls = get_parser_class("ouster_dome128")
            # クラスが取れた → ouster-sdk がインストールされている環境
            assert cls is not None
        except ImportError:
            # ouster-sdk が無い環境 → 正常にガードされている
            pass

    def test_ouster_parser_not_found(self):
        from cepf_sdk.errors import ParserNotFoundError
        from cepf_sdk.parsers import get_parser_class
        with pytest.raises(ParserNotFoundError):
            get_parser_class("nonexistent_parser")


# ---------------------------------------------------------------------------
# 結合テスト (ouster-sdk 必要)
# ---------------------------------------------------------------------------

@requires_ouster
class TestOusterBaseParserInit:
    """OusterBaseParser / OusterLidarParser の初期化テスト"""

    def test_instantiation(self):
        """デフォルト設定でインスタンス化できる"""
        from cepf_sdk.parsers.ouster import OusterLidarParser
        parser = OusterLidarParser()
        assert parser is not None

    def test_set_sensor_info(self):
        """set_sensor_info() で SensorInfo が登録される"""
        from cepf_sdk.parsers.ouster import OusterLidarParser
        info = _make_sensor_info()
        parser = OusterLidarParser()
        parser.set_sensor_info(info)
        assert parser.sensor_info is info
        assert parser.model_name == info.prod_line
        assert parser.columns_per_frame == info.format.columns_per_frame
        assert parser.pixels_per_column == info.format.pixels_per_column

    def test_parse_bytes_raises(self):
        """parse(bytes) は NotImplementedError を上げる"""
        from cepf_sdk.parsers.ouster import OusterLidarParser
        parser = OusterLidarParser()
        with pytest.raises(NotImplementedError):
            parser.parse(b"dummy")

    def test_validate_always_true(self):
        """validate() は常に True"""
        from cepf_sdk.parsers.ouster import OusterLidarParser
        parser = OusterLidarParser()
        assert parser.validate(b"any") is True


@requires_ouster
class TestOusterParseScan:
    """OusterLidarParser.parse_scan() の結合テスト"""

    def setup_method(self):
        from cepf_sdk.parsers.ouster import OusterLidarParser
        self.info = _make_sensor_info()
        self.parser = OusterLidarParser()
        self.parser.set_sensor_info(self.info)
        self.scan = _make_scan(self.info)

    def test_returns_cepf_frame(self):
        """parse_scan() が CepfFrame を返す"""
        from cepf_sdk.frame import CepfFrame
        frame = self.parser.parse_scan(self.scan)
        assert isinstance(frame, CepfFrame)

    def test_point_count(self):
        """点数 = H × W"""
        H = self.info.format.pixels_per_column
        W = self.info.format.columns_per_frame
        frame = self.parser.parse_scan(self.scan)
        assert frame.point_count == H * W

    def test_cartesian_fields_present(self):
        """デフォルト (CARTESIAN) モードで x, y, z が含まれる"""
        frame = self.parser.parse_scan(self.scan)
        for key in ("x", "y", "z"):
            assert key in frame.points

    def test_range_converted_to_meters(self):
        """RANGE フィールドが mm → m に変換されている"""
        from cepf_sdk.enums import CoordinateMode
        frame = self.parser.parse_scan(self.scan, CoordinateMode.CARTESIAN_WITH_RANGE)
        # 設定値 5000 mm → 5.0 m
        assert "range" in frame.points
        np.testing.assert_allclose(frame.points["range"], 5.0, atol=1e-3)

    def test_intensity_normalized(self):
        """REFLECTIVITY が [0, 1] に正規化されている"""
        frame = self.parser.parse_scan(self.scan)
        intensity = frame.points["intensity"]
        assert float(intensity.min()) >= 0.0
        assert float(intensity.max()) <= 1.0

    def test_confidence_range(self):
        """confidence が [0, 1] に収まる"""
        frame = self.parser.parse_scan(self.scan)
        conf = frame.points["confidence"]
        assert float(conf.min()) >= 0.0
        assert float(conf.max()) <= 1.0

    def test_flags_all_valid(self):
        """flags フィールドが全点 VALID フラグを持つ"""
        from cepf_sdk.enums import PointFlag
        frame = self.parser.parse_scan(self.scan)
        flags = frame.points["flags"]
        assert np.all(flags & PointFlag.VALID)

    def test_frame_id_increments(self):
        """連続 parse_scan() でフレーム ID が増加する"""
        f1 = self.parser.parse_scan(self.scan)
        f2 = self.parser.parse_scan(self.scan)
        assert f2.metadata.frame_id == f1.metadata.frame_id + 1

    def test_metadata_fields(self):
        """メタデータの基本フィールドが設定されている"""
        frame = self.parser.parse_scan(self.scan)
        meta = frame.metadata
        assert meta.coordinate_system == "sensor_local"
        assert meta.coordinate_mode == "cartesian"
        assert meta.sensor["type"] == "lidar"
        assert frame.format == "CEPF"
        assert frame.version == "1.4.0"

    def test_spherical_mode(self):
        """SPHERICAL モードで azimuth, elevation, range が含まれる"""
        from cepf_sdk.enums import CoordinateMode
        frame = self.parser.parse_scan(self.scan, CoordinateMode.SPHERICAL)
        for key in ("azimuth", "elevation", "range"):
            assert key in frame.points
        assert "x" not in frame.points

    def test_both_mode(self):
        """BOTH モードで XYZ と球面座標が両方含まれる"""
        from cepf_sdk.enums import CoordinateMode
        frame = self.parser.parse_scan(self.scan, CoordinateMode.BOTH)
        for key in ("x", "y", "z", "azimuth", "elevation", "range"):
            assert key in frame.points


@requires_ouster
class TestOusterDome128Parser:
    """OusterDome128Parser の固有設定テスト"""

    def test_instantiation(self):
        from cepf_sdk.parsers.ouster_dome128 import OusterDome128Parser
        parser = OusterDome128Parser()
        assert parser is not None
        assert parser.config.num_channels == 128

    def test_parse_scan(self):
        """OusterDome128Parser でも parse_scan() が動作する"""
        from cepf_sdk.parsers.ouster_dome128 import OusterDome128Parser
        from cepf_sdk.frame import CepfFrame
        info = _make_sensor_info()
        parser = OusterDome128Parser()
        parser.set_sensor_info(info)
        scan = _make_scan(info)
        frame = parser.parse_scan(scan)
        assert isinstance(frame, CepfFrame)


@requires_ouster
class TestOusterSensorInfoWithoutSet:
    """set_sensor_info() なし状態のエラーハンドリング"""

    def test_parse_scan_without_sensor_info_raises(self):
        """set_sensor_info() 前に parse_scan() を呼ぶと ConfigurationError"""
        from cepf_sdk.errors import ConfigurationError
        from cepf_sdk.parsers.ouster import OusterLidarParser
        info = _make_sensor_info()
        parser = OusterLidarParser()
        # sensor_info 未設定のまま実行
        scan = _make_scan(info)
        with pytest.raises(ConfigurationError):
            parser.parse_scan(scan)
