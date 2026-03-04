# tests/test_parsers/test_velodyne.py
"""Velodyne VLP-16 パーサーのテスト"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, SensorType
from cepf_sdk.errors import ParseError
from cepf_sdk.parsers.velodyne import (
    BLOCK_FLAG,
    BLOCKS_PER_PACKET,
    BLOCK_SIZE,
    CHANNELS_PER_BLOCK,
    PACKET_SIZE,
    VelodyneLidarParser,
)


def _build_vlp16_packet(all_zero: bool = False) -> bytes:
    """テスト用 VLP-16 パケット (1206 bytes) を構築する。"""
    buf = bytearray(PACKET_SIZE)
    for bi in range(BLOCKS_PER_PACKET):
        base = bi * BLOCK_SIZE
        struct.pack_into('<H', buf, base, BLOCK_FLAG)              # flag
        struct.pack_into('<H', buf, base + 2, bi * 3000)          # azimuth (30 deg steps)
        if not all_zero:
            for ci in range(CHANNELS_PER_BLOCK):
                ch_base = base + 4 + ci * 3
                struct.pack_into('<H', buf, ch_base, 500)          # 500 * 0.002 = 1.0 m
                buf[ch_base + 2] = 128                             # intensity
    # Timestamp at byte 1200, factory bytes at 1204-1205
    struct.pack_into('<I', buf, 1200, 123456)
    buf[1204] = 0x37  # strongest return
    buf[1205] = 0x21  # VLP-16
    return bytes(buf)


def _build_vlp32_packet() -> bytes:
    """テスト用 VLP-32C パケット (1206 bytes) を構築する。"""
    buf = bytearray(PACKET_SIZE)
    for bi in range(BLOCKS_PER_PACKET):
        base = bi * BLOCK_SIZE
        struct.pack_into('<H', buf, base, BLOCK_FLAG)
        struct.pack_into('<H', buf, base + 2, bi * 3000)
        for ci in range(CHANNELS_PER_BLOCK):
            ch_base = base + 4 + ci * 3
            struct.pack_into('<H', buf, ch_base, 1000)  # 2.0 m
            buf[ch_base + 2] = 200
    return bytes(buf)


class TestVelodyneLidarParserValidate:
    def test_wrong_size_returns_false(self):
        parser = VelodyneLidarParser()
        assert parser.validate(b"\x00" * 100) is False

    def test_short_packet_returns_false(self):
        parser = VelodyneLidarParser()
        assert parser.validate(b"\x00" * (PACKET_SIZE - 1)) is False

    def test_correct_size_returns_true(self):
        parser = VelodyneLidarParser()
        assert parser.validate(b"\x00" * PACKET_SIZE) is True

    def test_valid_packet_returns_true(self):
        parser = VelodyneLidarParser()
        pkt = _build_vlp16_packet()
        assert parser.validate(pkt) is True


class TestVelodyneLidarParserParse:
    def _make_parser(self) -> VelodyneLidarParser:
        config = SensorConfig(
            sensor_type=SensorType.LIDAR,
            model="Velodyne VLP-16",
            num_channels=16,
            max_range_m=100.0,
        )
        return VelodyneLidarParser(config=config)

    def test_wrong_size_raises_parse_error(self):
        parser = self._make_parser()
        with pytest.raises(ParseError):
            parser.parse(b"\x00" * 100)

    def test_all_zero_distances_raises_parse_error(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet(all_zero=True)
        with pytest.raises(ParseError):
            parser.parse(pkt)

    def test_returns_cepf_frame(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt)
        assert frame.format == "CEPF"
        assert frame.version == "1.4.0"
        assert frame.point_count > 0

    def test_cartesian_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN)
        assert "x" in frame.points
        assert "y" in frame.points
        assert "z" in frame.points
        assert "azimuth" not in frame.points
        assert "range" not in frame.points

    def test_spherical_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.SPHERICAL)
        assert "azimuth" in frame.points
        assert "elevation" in frame.points
        assert "range" in frame.points
        assert "x" not in frame.points

    def test_both_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.BOTH)
        assert "x" in frame.points
        assert "azimuth" in frame.points
        assert "elevation" in frame.points
        assert "range" in frame.points

    def test_cartesian_with_range_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN_WITH_RANGE)
        assert "x" in frame.points
        assert "range" in frame.points

    def test_standard_fields_present(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt)
        for field in ("timestamp", "intensity", "velocity", "confidence", "return_id", "flags"):
            assert field in frame.points, f"missing field: {field}"

    def test_distances_approximately_one_meter(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.SPHERICAL)
        ranges = np.asarray(frame.points["range"])
        assert np.allclose(ranges, 1.0, atol=1e-3)

    def test_intensity_normalized(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt)
        inten = np.asarray(frame.points["intensity"])
        assert np.all(inten >= 0.0)
        assert np.all(inten <= 1.0)

    def test_frame_id_increments(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        f1 = parser.parse(pkt)
        f2 = parser.parse(pkt)
        assert f2.metadata.frame_id > f1.metadata.frame_id

    def test_metadata_sensor_info(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt)
        assert frame.metadata.sensor is not None
        assert frame.metadata.sensor["model"] == "Velodyne VLP-16"
        assert frame.metadata.sensor["type"] == "lidar"

    def test_extensions_channel_id(self):
        parser = self._make_parser()
        pkt = _build_vlp16_packet()
        frame = parser.parse(pkt)
        assert frame.extensions is not None
        assert "lidar" in frame.extensions
        assert "channel_id" in frame.extensions["lidar"]
        ch = frame.extensions["lidar"]["channel_id"]
        assert len(ch) == frame.point_count


class TestVelodyneLidarParserVLP32:
    def _make_vlp32_parser(self) -> VelodyneLidarParser:
        config = SensorConfig(
            sensor_type=SensorType.LIDAR,
            model="Velodyne VLP-32C",
            num_channels=32,
            max_range_m=200.0,
        )
        return VelodyneLidarParser(config=config)

    def test_vlp32_parse_returns_frame(self):
        parser = self._make_vlp32_parser()
        pkt = _build_vlp32_packet()
        frame = parser.parse(pkt)
        assert frame.point_count > 0
        assert "x" in frame.points

    def test_vlp32_point_count(self):
        parser = self._make_vlp32_parser()
        pkt = _build_vlp32_packet()
        frame = parser.parse(pkt)
        # 12 blocks * 32 channels = 384 points (all non-zero)
        assert frame.point_count == BLOCKS_PER_PACKET * CHANNELS_PER_BLOCK
