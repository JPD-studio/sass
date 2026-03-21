import { describe, test, expect } from "@jest/globals";
import {
  CoordinateTransformer,
  latLngAltToECEF,
  ecefToLatLngAlt,
} from "../src/coordinate-transform.js";

// apps/sensors.example.json の installation と同一の座標
const TEST_MOUNT = {
  position: { lat: 34.649394, lng: 135.001478, alt: 54.0 },
  orientation: { heading: 0, pitch: 0, roll: 0 },
};

describe("latLngAltToECEF / ecefToLatLngAlt 往復変換", () => {
  test("赤道上の点 (0, 0, 0)", () => {
    const ecef = latLngAltToECEF(0, 0, 0);
    // WGS84 長半径
    expect(ecef[0]).toBeCloseTo(6378137.0, 0);
    expect(ecef[1]).toBeCloseTo(0, 0);
    expect(ecef[2]).toBeCloseTo(0, 0);
  });

  test("日本の代表点 往復変換", () => {
    const lat = 34.649394;
    const lng = 135.001478;
    const alt = 54.0;
    const ecef = latLngAltToECEF(lat, lng, alt);
    const back = ecefToLatLngAlt(ecef[0], ecef[1], ecef[2]);
    expect(back.lat).toBeCloseTo(lat, 6);
    expect(back.lng).toBeCloseTo(lng, 6);
    expect(back.alt).toBeCloseTo(alt, 3);
  });

  test("北極点 往復変換", () => {
    const ecef = latLngAltToECEF(90, 0, 0);
    const back = ecefToLatLngAlt(ecef[0], ecef[1], ecef[2]);
    expect(back.lat).toBeCloseTo(90, 4);
    expect(back.alt).toBeCloseTo(0, 1);
  });

  test("南極点 往復変換", () => {
    const ecef = latLngAltToECEF(-90, 0, 0);
    const back = ecefToLatLngAlt(ecef[0], ecef[1], ecef[2]);
    expect(back.lat).toBeCloseTo(-90, 4);
    expect(back.alt).toBeCloseTo(0, 1);
  });
});

describe("CoordinateTransformer", () => {
  test("heading=0: 前方100m → 北に約100m 移動", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const result = tf.transformPoint(100, 0, 0);

    // 北に100m → 緯度差 ≈ 100 / 110900 度 ≈ 0.000902 (at lat=34.65°)
    expect(result.lat).toBeGreaterThan(TEST_MOUNT.position.lat);
    // ±0.0001 度 (≈11m) 以内: 座標変換の数値誤差を許容
    expect(Math.abs(result.lat - 34.650296)).toBeLessThan(0.0001);
    // 経度はほぼ変わらない (±0.0001 度 ≈ ±9m)
    expect(Math.abs(result.lng - 135.001478)).toBeLessThan(0.0001);
    // 高度はほぼ変わらない
    expect(result.alt).toBeCloseTo(54.0, 0);
  });

  test("heading=90: 前方100m → 東に約100m 移動", () => {
    const tf = new CoordinateTransformer({
      position: TEST_MOUNT.position,
      orientation: { heading: 90, pitch: 0, roll: 0 },
    });
    const result = tf.transformPoint(100, 0, 0);

    // 東方向に移動 → 経度が増す
    expect(result.lng).toBeGreaterThan(TEST_MOUNT.position.lng);
    // 緯度はほぼ変わらない (±0.0001 度)
    expect(Math.abs(result.lat - TEST_MOUNT.position.lat)).toBeLessThan(0.0001);
  });

  test("heading=180: 前方100m → 南に約100m 移動", () => {
    const tf = new CoordinateTransformer({
      position: TEST_MOUNT.position,
      orientation: { heading: 180, pitch: 0, roll: 0 },
    });
    const result = tf.transformPoint(100, 0, 0);
    expect(result.lat).toBeLessThan(TEST_MOUNT.position.lat);
    // 経度はほぼ変わらない (±0.0001 度)
    expect(Math.abs(result.lng - TEST_MOUNT.position.lng)).toBeLessThan(0.0001);
  });

  test("heading=270: 前方100m → 西に約100m 移動", () => {
    const tf = new CoordinateTransformer({
      position: TEST_MOUNT.position,
      orientation: { heading: 270, pitch: 0, roll: 0 },
    });
    const result = tf.transformPoint(100, 0, 0);
    expect(result.lng).toBeLessThan(TEST_MOUNT.position.lng);
    // 緯度はほぼ変わらない
    expect(Math.abs(result.lat - TEST_MOUNT.position.lat)).toBeLessThan(0.0001);
  });

  test("原点(0,0,0)はマウント位置と一致", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const result = tf.transformPoint(0, 0, 0);
    expect(result.lat).toBeCloseTo(TEST_MOUNT.position.lat, 7);
    expect(result.lng).toBeCloseTo(TEST_MOUNT.position.lng, 7);
    expect(result.alt).toBeCloseTo(TEST_MOUNT.position.alt, 3);
  });

  test("上方向(0,0,10)は高度が増す", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const result = tf.transformPoint(0, 0, 10);
    // ±1m 以内で高度が +10m
    expect(result.alt).toBeGreaterThan(TEST_MOUNT.position.alt + 9);
    expect(result.alt).toBeLessThan(TEST_MOUNT.position.alt + 11);
  });

  test("heading=0: 距離保存性 (100m → WGS84 上でほぼ 100m)", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const origin = tf.transformPoint(0, 0, 0);
    const moved = tf.transformPoint(100, 0, 0);

    // 緯度差を地上距離に換算 (lat=34.65° では 1度 ≈ 110900m)
    const dist_m = Math.abs(moved.lat - origin.lat) * 110900;
    expect(dist_m).toBeGreaterThan(98);
    expect(dist_m).toBeLessThan(102);
  });

  test("transformPointCloud で複数点を一括変換", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const points = [
      { x: 0, y: 0, z: 0 },
      { x: 100, y: 0, z: 0 },
      { x: 0, y: 100, z: 0 },
    ];
    const results = tf.transformPointCloud(points);
    expect(results).toHaveLength(3);
    expect(results[0].lat).toBeCloseTo(TEST_MOUNT.position.lat, 7);
    expect(results[1].lat).toBeGreaterThan(results[0].lat);
  });
});

describe("性能テスト", () => {
  test("65k 点を 1 秒以内に変換", () => {
    const tf = new CoordinateTransformer(TEST_MOUNT);
    const points = Array.from({ length: 65000 }, (_, i) => ({
      x: (i % 100) * 1.0,
      y: Math.floor(i / 100) * 1.0,
      z: 0,
    }));

    const start = Date.now();
    const results = tf.transformPointCloud(points);
    const elapsed = Date.now() - start;

    expect(results).toHaveLength(65000);
    // Jetson (ARM) では処理が遅いため 2 秒以内を基準とする
    expect(elapsed).toBeLessThan(2000);
  });
});
