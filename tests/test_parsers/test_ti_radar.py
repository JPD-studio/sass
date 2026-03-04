# tests/test_parsers/test_ti_radar.py
"""TI AWR/IWR Radar パーサーのテスト"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, SensorType
from cepf_sdk.errors import ParseError
from cepf_sdk.parsers.ti_radar import (
    HEADER_SIZE,
    MAGIC_WORD,
    TLV_HEADER_SIZE,
    TLV_TYPE_DETECTED_POINTS,
    TLV_TYPE_SIDE_INFO,
    TIRadarParser,
)


def _build_ti_packet(
    n_points: int = 3,
    include_side_info: bool = False,
    ego_velocity: float = 0.0,
) -> bytes:
    """テスト用 TI mmWave パケットを構築する。"""
    # TLV type 1: detected points (x, y, z, doppler)
    tlv1_values = []
    for i in range(n_points):
        tlv1_values.extend([float(i + 1), float((i + 1) * 2), 0.5, float(i) * 0.5])
    tlv1_data = struct.pack(f'<{len(tlv1_values)}f', *tlv1_values)
    tlv1 = struct.pack('<II', TLV_TYPE_DETECTED_POINTS, len(tlv1_data)) + tlv1_data

    tlvs = tlv1
    num_tlvs = 1

    if include_side_info:
        # TLV type 7: SNR + noise per point
        side_values = []
        for i in range(n_points):
            side_values.extend([i * 100, 50])  # snr, noise (int16)
        tlv7_data = struct.pack(f'<{len(side_values)}h', *side_values)
        tlv7 = struct.pack('<II', TLV_TYPE_SIDE_INFO, len(tlv7_data)) + tlv7_data
        tlvs += tlv7
        num_tlvs = 2

    total_len = HEADER_SIZE + len(tlvs)
    header_payload = struct.pack(
        '<IIIIIIII',
        0x01020304,   # version
        total_len,    # totalPacketLen
        0xA1642,      # platform (AWR1843)
        1,            # frameNumber
        0,            # timeCpuCycles
        n_points,     # numDetectedObj
        num_tlvs,     # numTLVs
        0,            # subFrameNumber
    )

    return MAGIC_WORD + header_payload + tlvs


class TestTIRadarParserValidate:
    def test_wrong_magic_returns_false(self):
        parser = TIRadarParser()
        assert parser.validate(b"\x00" * 40) is False

    def test_too_short_returns_false(self):
        parser = TIRadarParser()
        assert parser.validate(MAGIC_WORD[:4]) is False

    def test_valid_magic_returns_true(self):
        parser = TIRadarParser()
        pkt = _build_ti_packet()
        assert parser.validate(pkt) is True


class TestTIRadarParserParse:
    def _make_parser(self) -> TIRadarParser:
        config = SensorConfig(
            sensor_type=SensorType.RADAR,
            model="TI AWR1843",
            max_range_m=50.0,
        )
        return TIRadarParser(config=config)

    def test_invalid_magic_raises_parse_error(self):
        parser = self._make_parser()
        with pytest.raises(ParseError):
            parser.parse(b"\x00" * HEADER_SIZE)

    def test_returns_cepf_frame(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt)
        assert frame.format == "CEPF"
        assert frame.version == "1.4.0"

    def test_point_count_matches(self):
        parser = self._make_parser()
        for n in (1, 5, 10):
            pkt = _build_ti_packet(n_points=n)
            frame = parser.parse(pkt)
            assert frame.point_count == n, f"expected {n} points, got {frame.point_count}"

    def test_cartesian_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN)
        assert "x" in frame.points
        assert "y" in frame.points
        assert "z" in frame.points
        assert "azimuth" not in frame.points

    def test_spherical_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.SPHERICAL)
        assert "azimuth" in frame.points
        assert "elevation" in frame.points
        assert "range" in frame.points
        assert "x" not in frame.points

    def test_both_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.BOTH)
        assert "x" in frame.points
        assert "azimuth" in frame.points
        assert "range" in frame.points

    def test_cartesian_with_range_mode_fields(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN_WITH_RANGE)
        assert "x" in frame.points
        assert "range" in frame.points
        assert "azimuth" not in frame.points

    def test_standard_fields_present(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt)
        for field in ("timestamp", "intensity", "velocity", "confidence", "return_id", "flags"):
            assert field in frame.points, f"missing field: {field}"

    def test_intensity_default_ones_without_side_info(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3, include_side_info=False)
        frame = parser.parse(pkt)
        inten = np.asarray(frame.points["intensity"])
        assert np.all(inten == 1.0)

    def test_intensity_from_side_info(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3, include_side_info=True)
        frame = parser.parse(pkt)
        inten = np.asarray(frame.points["intensity"])
        # SNR = [0, 100, 200] → intensity = [0/1000, 0.1, 0.2]
        assert inten[0] == pytest.approx(0.0, abs=1e-4)
        assert 0.0 <= float(inten[1]) <= 1.0

    def test_ego_velocity_compensation(self):
        parser = self._make_parser()
        parser.set_ego_velocity(5.0)
        pkt = _build_ti_packet(n_points=3)
        frame = parser.parse(pkt)
        vel = np.asarray(frame.points["velocity"])
        # raw doppler for point 0 = 0.0, after compensation = 0.0 - 5.0 = -5.0
        assert vel[0] == pytest.approx(-5.0, abs=1e-4)

    def test_frame_id_increments(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=2)
        f1 = parser.parse(pkt)
        f2 = parser.parse(pkt)
        assert f2.metadata.frame_id > f1.metadata.frame_id

    def test_metadata_sensor_info(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=2)
        frame = parser.parse(pkt)
        assert frame.metadata.sensor is not None
        assert frame.metadata.sensor["model"] == "TI AWR1843"
        assert frame.metadata.sensor["type"] == "radar"

    def test_extensions_radar_info(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=2)
        frame = parser.parse(pkt)
        assert frame.extensions is not None
        assert "radar" in frame.extensions
        radar_ext = frame.extensions["radar"]
        assert radar_ext["frame_number"] == 1
        assert radar_ext["num_detected_objects"] == 2

    def test_data_shorter_than_total_len_raises(self):
        parser = self._make_parser()
        pkt = _build_ti_packet(n_points=3)
        # Truncate to fewer bytes than total_len declares
        with pytest.raises(ParseError):
            parser.parse(pkt[:HEADER_SIZE + 4])
