#!/usr/bin/env python3
"""Minimal test runner (pytest not available)"""
import sys
import traceback

sys.path.insert(0, ".")

import json
import math
import struct

import numpy as np

from cepf_sdk.config import InstallationInfo, SensorConfig, Transform
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, PointFlag, SensorType
from cepf_sdk.errors import ParseError, SensorNotFoundError, ValidationError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from dataclasses import replace

passed = 0
failed = 0

def run(name, func):
    global passed, failed
    try:
        func()
        print(f"  PASS: {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {name} -- {e}")
        traceback.print_exc()
        failed += 1

def eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


# ===== ENUMS =====
print("=== test_enums ===")

def t_sensor_type():
    eq(SensorType.LIDAR.value, 1)
    eq(SensorType.RADAR.value, 2)
run("SensorType", t_sensor_type)

def t_coord_sys():
    eq(CoordinateSystem.SENSOR_LOCAL, "sensor_local")
    assert isinstance(CoordinateSystem.SENSOR_LOCAL, str)
run("CoordinateSystem", t_coord_sys)

def t_coord_mode():
    eq(CoordinateMode.CARTESIAN, "cartesian")
    eq(CoordinateMode.BOTH, "both")
run("CoordinateMode", t_coord_mode)

def t_flags():
    eq(PointFlag.VALID, 0x0001)
    eq(PointFlag.GROUND, 0x0004)
    combined = PointFlag.VALID | PointFlag.GROUND
    assert combined & PointFlag.VALID
    assert combined & PointFlag.GROUND
    assert not (combined & PointFlag.NOISE)
run("PointFlag", t_flags)


# ===== FRAME =====
print("\n=== test_frame ===")

def make_frame(n=100):
    rng = np.random.default_rng(42)
    meta = CepfMetadata(
        timestamp_utc="2026-03-03T12:00:00Z", frame_id=1,
        coordinate_system="sensor_local", coordinate_mode="cartesian",
        units={"position": "meters"},
    )
    pts = {
        "x": rng.uniform(-10, 10, n).astype(np.float32),
        "y": rng.uniform(-10, 10, n).astype(np.float32),
        "z": rng.uniform(-2, 5, n).astype(np.float32),
        "intensity": rng.uniform(0, 1, n).astype(np.float32),
        "flags": np.full(n, PointFlag.VALID, dtype=np.uint16),
    }
    return CepfFrame(
        format="CEPF", version="1.4.0", metadata=meta,
        schema={"fields": ["x","y","z","intensity","flags"]},
        points=pts, point_count=n,
    )

def t_frozen():
    meta = CepfMetadata("", 0, "sensor_local", "cartesian", {})
    try:
        meta.frame_id = 99
        assert False, "Should raise"
    except (AttributeError, TypeError):
        pass
run("CepfMetadata frozen", t_frozen)

def t_frame_frozen():
    f = make_frame()
    try:
        f.point_count = 0
        assert False
    except (AttributeError, TypeError):
        pass
run("CepfFrame frozen", t_frame_frozen)

def t_to_json():
    f = make_frame(10)
    j = f.to_json()
    obj = json.loads(j)
    eq(obj["format"], "CEPF")
    eq(obj["point_count"], 10)
    assert "x" in obj["points"]
run("to_json", t_to_json)

def t_from_json():
    f = make_frame(5)
    j = f.to_json()
    r = CepfFrame.from_json(j)
    eq(r.format, "CEPF")
    eq(r.point_count, 5)
    np.testing.assert_allclose(np.asarray(r.points["x"]),
                               np.asarray(f.points["x"]), atol=1e-4)
run("from_json roundtrip", t_from_json)

def t_to_binary():
    f = make_frame(10)
    b = f.to_binary()
    assert b[:4] == b"CEPF"
    assert len(b) >= 32
run("to_binary header", t_to_binary)

def t_filter_flags():
    f = make_frame(100)
    flags = np.asarray(f.points["flags"]).copy()
    flags[10:30] |= PointFlag.GROUND
    f2 = replace(f, points={**f.points, "flags": flags})
    filtered = f2.filter_by_flags(exclude=PointFlag.GROUND)
    eq(filtered.point_count, 80)
    ground = f2.filter_by_flags(include=PointFlag.GROUND)
    eq(ground.point_count, 20)
run("filter_by_flags", t_filter_flags)

def t_transform():
    f = make_frame(50)
    t = Transform(
        translation=np.array([1.0, 2.0, 3.0], dtype=np.float64),
        rotation_quaternion=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
    )
    f2 = f.transform_points(t)
    np.testing.assert_allclose(np.asarray(f2.points["x"]),
                               np.asarray(f.points["x"]) + 1.0, atol=1e-4)
    np.testing.assert_allclose(np.asarray(f2.points["y"]),
                               np.asarray(f.points["y"]) + 2.0, atol=1e-4)
    np.testing.assert_allclose(np.asarray(f2.points["z"]),
                               np.asarray(f.points["z"]) + 3.0, atol=1e-4)
run("transform_points", t_transform)


# ===== COORDINATES =====
print("\n=== test_coordinates ===")
from cepf_sdk.utils.coordinates import (
    spherical_to_cartesian, cartesian_to_spherical, lla_to_ecef, ecef_to_lla,
)

def t_sph_identity():
    x, y, z = spherical_to_cartesian(1.0, 0.0, 0.0)
    assert abs(x - 1.0) < 1e-10
    assert abs(y) < 1e-10
    assert abs(z) < 1e-10
run("sph→cart identity", t_sph_identity)

def t_sph_roundtrip():
    r, az, el = 5.0, 45.0, 30.0
    x, y, z = spherical_to_cartesian(r, az, el)
    r2, az2, el2 = cartesian_to_spherical(x, y, z)
    assert abs(r - r2) < 1e-8
    assert abs(az - az2) < 1e-8
    assert abs(el - el2) < 1e-8
run("sph↔cart roundtrip", t_sph_roundtrip)

def t_lla_ecef():
    lat, lon, alt = 35.6762, 139.6503, 220.5
    x, y, z = lla_to_ecef(lat, lon, alt)
    lat2, lon2, alt2 = ecef_to_lla(x, y, z)
    assert abs(lat - lat2) < 1e-8
    assert abs(lon - lon2) < 1e-8
    assert abs(alt - alt2) < 0.01
run("lla↔ecef roundtrip", t_lla_ecef)

def t_equator():
    x, y, z = lla_to_ecef(0.0, 0.0, 0.0)
    assert abs(y) < 1e-3
    assert abs(z) < 1e-3
    assert abs(x - 6378137.0) < 1.0
run("equator prime meridian", t_equator)


# ===== FILTERS =====
print("\n=== test_filters ===")
from cepf_sdk.filters.base import FilterMode
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.range.box import BoxFilter
from cepf_sdk.filters.range.spherical import SphericalFilter
from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.filters.statistical.voxel import VoxelDownsample
from cepf_sdk.filters.attribute.intensity import IntensityFilter
from cepf_sdk.filters.attribute.confidence import ConfidenceFilter
from cepf_sdk.filters.pipeline import FilterPipeline

def make_pts(n=500):
    rng = np.random.default_rng(42)
    return {
        "x": rng.uniform(-20, 20, n).astype(np.float32),
        "y": rng.uniform(-20, 20, n).astype(np.float32),
        "z": rng.uniform(-5, 30, n).astype(np.float32),
        "intensity": rng.uniform(0, 1, n).astype(np.float32),
    }

def t_cyl():
    pts = make_pts(1000)
    f = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0)
    r = f.apply(pts)
    assert r.count_after < r.count_before
    assert r.count_after > 0
run("CylindricalFilter basic", t_cyl)

def t_cyl_invert():
    pts = make_pts(1000)
    fn = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0)
    fi = CylindricalFilter(radius_m=5.0, z_min_m=-5.0, z_max_m=30.0, invert=True)
    rn = fn.apply(pts)
    ri = fi.apply(pts)
    eq(rn.count_after + ri.count_after, rn.count_before)
run("CylindricalFilter invert", t_cyl_invert)

def t_cyl_flag():
    pts = make_pts(100)
    pts["flags"] = np.zeros(100, dtype=np.uint16)
    f = CylindricalFilter(
        radius_m=5.0, z_min_m=-5.0, z_max_m=30.0,
        mode=FilterMode.FLAG, flag_bit=0x0004,
    )
    r = f.apply(pts)
    eq(r.count_after, r.count_before)
    flags = np.asarray(r.points["flags"])
    assert np.any(flags & 0x0004)
run("CylindricalFilter FLAG mode", t_cyl_flag)

def t_box():
    pts = make_pts(500)
    f = BoxFilter(x_min=-5, x_max=5, y_min=-5, y_max=5, z_min=-2, z_max=10)
    r = f.apply(pts)
    assert r.count_after < r.count_before
run("BoxFilter", t_box)

def t_spherical():
    pts = make_pts(500)
    f = SphericalFilter(radius_m=10.0)
    r = f.apply(pts)
    assert r.count_after < r.count_before
run("SphericalFilter", t_spherical)

def t_intensity():
    pts = make_pts(500)
    f = IntensityFilter(min_intensity=0.3, max_intensity=0.7)
    r = f.apply(pts)
    assert r.count_after < r.count_before
run("IntensityFilter", t_intensity)

def t_confidence():
    pts = make_pts(100)
    rng = np.random.default_rng(99)
    pts["confidence"] = rng.uniform(0, 1, 100).astype(np.float32)
    f = ConfidenceFilter(min_confidence=0.5)
    r = f.apply(pts)
    assert r.count_after < r.count_before
run("ConfidenceFilter", t_confidence)

def t_voxel():
    pts = make_pts(500)
    f = VoxelDownsample(voxel_size=5.0)
    r = f.apply(pts)
    assert r.count_after < r.count_before
    assert r.count_after > 0
run("VoxelDownsample", t_voxel)

def t_ror():
    rng = np.random.default_rng(42)
    cx = rng.normal(0, 0.1, 80).astype(np.float32)
    cy = rng.normal(0, 0.1, 80).astype(np.float32)
    cz = rng.normal(0, 0.1, 80).astype(np.float32)
    ox = rng.uniform(50, 100, 20).astype(np.float32)
    oy = rng.uniform(50, 100, 20).astype(np.float32)
    oz = rng.uniform(50, 100, 20).astype(np.float32)
    pts = {
        "x": np.concatenate([cx, ox]),
        "y": np.concatenate([cy, oy]),
        "z": np.concatenate([cz, oz]),
        "intensity": np.ones(100, dtype=np.float32),
    }
    f = RadiusOutlierRemoval(radius_m=1.0, min_neighbors=3)
    r = f.apply(pts)
    assert r.count_after < 100
    assert r.count_after >= 70
run("RadiusOutlierRemoval", t_ror)

def t_pipeline():
    pts = make_pts(500)
    p = FilterPipeline(filters=[
        BoxFilter(x_min=-10, x_max=10, y_min=-10, y_max=10, z_min=-10, z_max=30),
        IntensityFilter(min_intensity=0.3, max_intensity=0.8),
    ])
    r = p.apply(pts)
    assert r.count_after < 500
run("FilterPipeline chained", t_pipeline)

def t_pipeline_empty():
    p = FilterPipeline(filters=[])
    pts = make_pts(100)
    r = p.apply(pts)
    eq(r.count_after, 100)
run("FilterPipeline empty", t_pipeline_empty)


# ===== USC =====
print("\n=== test_usc ===")
from cepf_sdk.usc import UnifiedSenseCloud
from cepf_sdk.parsers.base import RawDataParser

class StubParser(RawDataParser):
    def parse(self, raw_data, coordinate_mode=None):
        n = 50
        rng = np.random.default_rng(0)
        mode = coordinate_mode or self._default_coordinate_mode
        pts = {
            "x": rng.uniform(-5, 5, n).astype(np.float32),
            "y": rng.uniform(-5, 5, n).astype(np.float32),
            "z": rng.uniform(0, 3, n).astype(np.float32),
            "intensity": rng.uniform(0, 1, n).astype(np.float32),
            "flags": np.full(n, PointFlag.VALID, dtype=np.uint16),
        }
        meta = CepfMetadata(
            timestamp_utc="2026-03-03T00:00:00Z", frame_id=self._next_frame_id(),
            coordinate_system="sensor_local",
            coordinate_mode=mode.value if hasattr(mode, "value") else str(mode),
            units={"position": "meters"},
            sensor={"type": "lidar", "model": self.config.model},
        )
        return CepfFrame(
            format="CEPF", version="1.4.0", metadata=meta,
            schema={"fields": list(pts.keys())}, points=pts, point_count=n,
        )

    def validate(self, raw_data):
        return isinstance(raw_data, bytes) and len(raw_data) > 0

UnifiedSenseCloud.register_parser("_stub", StubParser)

def t_add_forge():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    f = usc.forge("s1", b"\x01" * 10)
    assert isinstance(f, CepfFrame)
    eq(f.point_count, 50)
run("USC add_sensor+forge", t_add_forge)

def t_not_found():
    usc = UnifiedSenseCloud()
    try:
        usc.forge("nope", b"\x00")
        assert False
    except SensorNotFoundError:
        pass
run("USC sensor not found", t_not_found)

def t_val_fail():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    try:
        usc.forge("s1", b"")
        assert False
    except ValidationError:
        pass
run("USC validation fail", t_val_fail)

def t_forge_multi():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    usc.add_sensor("s2", "_stub", cfg)
    f = usc.forge_multi({"s1": b"\x01", "s2": b"\x02"})
    eq(f.point_count, 100)
    eq(len(f.points["x"]), 100)
run("USC forge_multi", t_forge_multi)

def t_get_parser():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    assert isinstance(usc.get_parser("s1"), StubParser)
    assert usc.get_parser("missing") is None
run("USC get_parser", t_get_parser)

def t_installation():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    usc.set_installation(InstallationInfo(
        reference_description="屋上", reference_latitude=35.6762,
        reference_longitude=139.6503, reference_altitude=220.5,
    ))
    f = usc.forge("s1", b"\x01")
    assert f.metadata.installation is not None
    eq(f.metadata.installation["reference_point"]["latitude"], 35.6762)
run("USC installation", t_installation)

def t_transform():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    usc.set_transform([10.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0])
    usc.set_output_coordinate(CoordinateSystem.WORLD_ENU)
    f = usc.forge("s1", b"\x01")
    eq(f.metadata.coordinate_system, "world_enu")
    assert f.metadata.transform_to_world is not None
run("USC transform", t_transform)

def t_filter():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    usc.add_sensor("s1", "_stub", cfg)
    def half_filter(frame):
        h = frame.point_count // 2
        new_pts = {k: np.asarray(v)[:h] for k, v in frame.points.items()}
        return replace(frame, points=new_pts, point_count=h)
    usc.add_filter(half_filter)
    f = usc.forge("s1", b"\x01")
    eq(f.point_count, 25)
run("USC filter", t_filter)

def t_fluent():
    usc = UnifiedSenseCloud()
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="Stub")
    assert usc.add_sensor("s1", "_stub", cfg) is usc
    assert usc.set_transform([0,0,0], [1,0,0,0]) is usc
    assert usc.set_output_coordinate(CoordinateSystem.SENSOR_LOCAL) is usc
    assert usc.set_output_coordinate_mode(CoordinateMode.CARTESIAN) is usc
    assert usc.set_installation(InstallationInfo()) is usc
    assert usc.add_filter(lambda f: f) is usc
run("USC fluent API", t_fluent)

def t_from_json():
    import tempfile
    config_dict = {
        "sensors": [{
            "sensor_id": "test_sensor",
            "parser_name": "_stub",
            "config": {"sensor_type": "LIDAR", "model": "TestLiDAR"},
        }]
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f)
        path = f.name
    usc = UnifiedSenseCloud.from_json(path)
    assert usc.get_parser("test_sensor") is not None
run("USC from_json", t_from_json)


# ===== AIRY PARSER =====
print("\n=== test_airy_parser ===")
from cepf_sdk.drivers.robosense_airy_driver import (
    decode_packet, validate_packet, PKT_LEN, FLAG_EXPECT,
    HDR, DB_SIZE, N_DB, CH_PER_DB,
)
from cepf_sdk.parsers.robosense_airy import RoboSenseAiryParser

def build_fake_pkt():
    buf = bytearray(PKT_LEN)
    struct.pack_into(">I", buf, 26, 123456)
    for dbi in range(N_DB):
        bs = HDR + dbi * DB_SIZE
        struct.pack_into(">H", buf, bs, FLAG_EXPECT)
        struct.pack_into(">H", buf, bs + 2, 18000)
        for ci in range(min(4, CH_PER_DB)):
            off = bs + 3 + ci * 3
            struct.pack_into(">H", buf, off, 500)
            buf[off + 2] = 128
    return bytes(buf)

def t_driver_decode():
    pkt = build_fake_pkt()
    r = decode_packet(pkt)
    assert r is not None
    assert len(r.azimuth_deg) > 0
    assert np.all(r.distance_m > 0)
run("driver decode_packet", t_driver_decode)

def t_driver_validate():
    pkt = build_fake_pkt()
    assert validate_packet(pkt) is True
    assert validate_packet(b"\x00" * 10) is False
    assert validate_packet(bytes(PKT_LEN)) is False  # no valid flags
run("driver validate_packet", t_driver_validate)

def t_airy_parse():
    cfg = SensorConfig(
        sensor_type=SensorType.LIDAR, model="RoboSense Airy",
        num_channels=96, max_range_m=200.0,
    )
    p = RoboSenseAiryParser(config=cfg)
    pkt = build_fake_pkt()
    f = p.parse(pkt)
    eq(f.format, "CEPF")
    assert f.point_count > 0
    assert "x" in f.points
run("Airy parse", t_airy_parse)

def t_airy_invalid():
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="RoboSense Airy")
    p = RoboSenseAiryParser(config=cfg)
    try:
        p.parse(b"\x00" * PKT_LEN)
        assert False
    except ParseError:
        pass
run("Airy invalid packet", t_airy_invalid)

def t_airy_modes():
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="RoboSense Airy")
    p = RoboSenseAiryParser(config=cfg)
    pkt = build_fake_pkt()

    fc = p.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN)
    assert "x" in fc.points
    assert "azimuth" not in fc.points

    fs = p.parse(pkt, coordinate_mode=CoordinateMode.SPHERICAL)
    assert "azimuth" in fs.points
    assert "x" not in fs.points

    fb = p.parse(pkt, coordinate_mode=CoordinateMode.BOTH)
    assert "x" in fb.points
    assert "azimuth" in fb.points

    fr = p.parse(pkt, coordinate_mode=CoordinateMode.CARTESIAN_WITH_RANGE)
    assert "x" in fr.points
    assert "range" in fr.points
run("Airy coordinate modes", t_airy_modes)

def t_airy_frame_id():
    cfg = SensorConfig(sensor_type=SensorType.LIDAR, model="RoboSense Airy")
    p = RoboSenseAiryParser(config=cfg)
    pkt = build_fake_pkt()
    f1 = p.parse(pkt)
    f2 = p.parse(pkt)
    assert f2.metadata.frame_id > f1.metadata.frame_id
run("Airy frame_id increments", t_airy_frame_id)


# ===== QUATERNION =====
print("\n=== test_quaternion ===")
from cepf_sdk.utils.quaternion import quaternion_to_rotation_matrix, rotation_matrix_to_quaternion

def t_identity_quat():
    R = quaternion_to_rotation_matrix(np.array([1, 0, 0, 0], dtype=np.float64))
    np.testing.assert_allclose(R, np.eye(3), atol=1e-10)
run("identity quaternion", t_identity_quat)

def t_quat_roundtrip():
    q = np.array([0.707, 0.0, 0.707, 0.0], dtype=np.float64)
    q = q / np.linalg.norm(q)
    R = quaternion_to_rotation_matrix(q)
    q2 = rotation_matrix_to_quaternion(R)
    # quaternions q and -q represent the same rotation
    if np.dot(q, q2) < 0:
        q2 = -q2
    np.testing.assert_allclose(q, q2, atol=1e-10)
run("quat↔matrix roundtrip", t_quat_roundtrip)


# ===== SUMMARY =====
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
print(f"{'='*40}")
sys.exit(1 if failed else 0)
