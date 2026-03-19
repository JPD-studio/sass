# tests/test_parsers/test_robosense_airy.py
"""RoboSense Airy パーサーのテスト"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from cepf_sdk.config import SensorConfig
from cepf_sdk.drivers.robosense_airy_driver import (
    AiryDriverConfig,
    AiryPacketData,
    CH_PER_DB,
    DB_SIZE,
    FLAG_EXPECT,
    HDR,
    N_DB,
    PKT_LEN,
    decode_packet,
    validate_packet,
)
from cepf_sdk.enums import CoordinateMode, SensorType
from cepf_sdk.errors import ParseError
from cepf_sdk.parsers.robosense_airy import RoboSenseAiryParser


def _build_fake_packet() -> bytes:
    """テスト用の最小有効パケットを構築する"""
    buf = bytearray(PKT_LEN)

    # timestamp (big-endian u32 at offset 26)
    struct.pack_into(">I", buf, 26, 123456)

    # Build 8 data blocks with valid flags and some distance data
    for dbi in range(N_DB):
        bs = HDR + dbi * DB_SIZE
        # Flag = 0xFFEE
        struct.pack_into(">H", buf, bs, FLAG_EXPECT)
        # Azimuth = 18000 → 180.00 deg
        struct.pack_into(">H", buf, bs + 2, 18000)
        # Write some channel data (first few channels)
        for ci in range(min(4, CH_PER_DB)):
            off = bs + 4 + ci * 3
            # distance word: 14-bit value = 500 (→ 500 * 0.002 = 1.0m)
            struct.pack_into(">H", buf, off, 500)
            # intensity = 128
            buf[off + 2] = 128

    return bytes(buf)


class TestDriverDecodePacket:
    def test_wrong_length_returns_none(self):
        assert decode_packet(b"\x00" * 100) is None

    def test_valid_packet(self):
        pkt = _build_fake_packet()
        result = decode_packet(pkt)
        assert result is not None
        assert isinstance(result, AiryPacketData)
        assert len(result.azimuth_deg) > 0
        assert len(result.distance_m) == len(result.azimuth_deg)

    def test_distances_are_positive(self):
        pkt = _build_fake_packet()
        result = decode_packet(pkt)
        assert result is not None
        assert np.all(result.distance_m > 0)

    def test_intensity_range(self):
        pkt = _build_fake_packet()
        result = decode_packet(pkt)
        assert result is not None
        assert np.all(result.intensity_raw <= 255)


class TestDriverValidatePacket:
    def test_wrong_length(self):
        assert validate_packet(b"\x00" * 10) is False

    def test_valid(self):
        pkt = _build_fake_packet()
        assert validate_packet(pkt) is True

    def test_no_valid_flags(self):
        buf = bytearray(PKT_LEN)
        # All data blocks have flag 0x0000 (invalid)
        assert validate_packet(bytes(buf)) is False


class TestRoboSenseAiryParser:
    def _make_parser(self) -> RoboSenseAiryParser:
        config = SensorConfig(
            sensor_type=SensorType.LIDAR,
            model="RoboSense Airy",
            num_channels=96,
            max_range_m=200.0,
        )
        return RoboSenseAiryParser(config=config)

    def test_parse_valid_packet(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt)
        assert frame.format == "CEPF"
        assert frame.version == "1.4.0"
        assert frame.point_count > 0
        assert "x" in frame.points
        assert "y" in frame.points
        assert "z" in frame.points

    def test_parse_invalid_raises(self):
        parser = self._make_parser()
        with pytest.raises(ParseError):
            parser.parse(b"\x00" * PKT_LEN)

    def test_validate(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        assert parser.validate(pkt) is True
        assert parser.validate(b"\x00" * 10) is False

    def test_coordinate_mode_cartesian(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN)
        assert "x" in frame.points
        assert "azimuth" not in frame.points

    def test_coordinate_mode_spherical(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.SPHERICAL)
        assert "azimuth" in frame.points
        assert "x" not in frame.points

    def test_coordinate_mode_both(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.BOTH)
        assert "x" in frame.points
        assert "azimuth" in frame.points

    def test_coordinate_mode_cartesian_with_range(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN_WITH_RANGE)
        assert "x" in frame.points
        assert "range" in frame.points

    def test_metadata_sensor_info(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        frame = parser.parse(pkt)
        assert frame.metadata.sensor is not None
        assert frame.metadata.sensor["model"] == "RoboSense Airy"

    def test_frame_id_increments(self):
        parser = self._make_parser()
        pkt = _build_fake_packet()
        f1 = parser.parse(pkt)
        f2 = parser.parse(pkt)
        assert f2.metadata.frame_id > f1.metadata.frame_id
