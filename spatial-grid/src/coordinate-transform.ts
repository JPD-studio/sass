/**
 * coordinate-transform.ts
 * センサーローカル XYZ → WGS84 座標変換パイプライン
 *
 * 変換ステップ:
 *   Step 1: センサーローカル XYZ → ENU (East-North-Up)
 *           R_sensor = Rz(90° - heading) × Ry(-pitch) × Rx(roll)
 *           P_enu = R_sensor × P_sensor
 *   Step 2: ENU → ECEF (回転行列)
 *           dECEF = R_enu2ecef × P_enu
 *   Step 3: ECEF 原点に加算
 *           ECEF = ECEF_origin + dECEF
 *   Step 4: ECEF → WGS84 (Heikkinen 反復法)
 *
 * ブラウザ互換: Node.js API 不使用 → geo-viewer (webpack) からも import 可
 *
 * cepf_sdk/utils/coordinates.py の TS 版
 */

import { MountPosition, MountOrientation } from "./types.js";
import { eulerToQuaternion, quaternionToRotationMatrix } from "./euler-quaternion.js";

// WGS84 楕円体パラメータ
const WGS84_A = 6378137.0;            // 長半径 [m]
const WGS84_F = 1 / 298.257223563;    // 扁平率
const WGS84_E2 = 2 * WGS84_F - WGS84_F * WGS84_F; // 離心率の二乗

export class CoordinateTransformer {
  private readonly R_sensor: number[][];    // センサーローカル→ENU 回転行列
  private readonly R_enu2ecef: number[][];  // ENU→ECEF 回転行列
  private readonly ecef_origin: number[];   // マウント位置の ECEF 座標キャッシュ

  constructor(mount: { position: MountPosition; orientation: MountOrientation }) {
    this.R_sensor = this._computeSensorRotation(mount.orientation);
    this.R_enu2ecef = this._computeENUtoECEF(mount.position);
    this.ecef_origin = latLngAltToECEF(
      mount.position.lat,
      mount.position.lng,
      mount.position.alt
    );
  }

  /** センサーの Euler 角からセンサーローカル→ENU 回転行列を算出 */
  private _computeSensorRotation(orientation: MountOrientation): number[][] {
    const q = eulerToQuaternion(
      orientation.heading,
      orientation.pitch,
      orientation.roll
    );
    return quaternionToRotationMatrix(q);
  }

  /** マウント位置 (lat₀, lng₀) から ENU→ECEF 回転行列を算出（コンストラクタで一度だけ）
   *
   * 各列が ENU 基底ベクトルの ECEF 表現:
   *   列0 (East):  [-sinL,         cosL,        0    ]
   *   列1 (North): [-sinP*cosL,   -sinP*sinL,   cosP ]
   *   列2 (Up):    [ cosP*cosL,    cosP*sinL,   sinP ]
   *
   * dECEF = R × [E, N, U]^T
   */
  private _computeENUtoECEF(position: MountPosition): number[][] {
    const phi = (position.lat * Math.PI) / 180;
    const lam = (position.lng * Math.PI) / 180;
    const sinP = Math.sin(phi);
    const cosP = Math.cos(phi);
    const sinL = Math.sin(lam);
    const cosL = Math.cos(lam);
    return [
      [-sinL,          -sinP * cosL,   cosP * cosL ],
      [ cosL,          -sinP * sinL,   cosP * sinL ],
      [ 0,              cosP,          sinP        ],
    ];
  }

  /**
   * センサーローカル 1 点を WGS84 座標に変換
   * GC 圧力を避けるため、呼び出し側で事前確保したバッファに書き込むことを推奨
   */
  transformPoint(x: number, y: number, z: number): { lat: number; lng: number; alt: number } {
    // Step 1: センサーローカル → ENU
    const [e, n, u] = _mat3MulVec(this.R_sensor, x, y, z);

    // Step 2: ENU → ECEF 変位
    const [dx, dy, dz] = _mat3MulVec(this.R_enu2ecef, e, n, u);

    // Step 3: ECEF 原点に加算
    const ex = this.ecef_origin[0] + dx;
    const ey = this.ecef_origin[1] + dy;
    const ez = this.ecef_origin[2] + dz;

    // Step 4: ECEF → WGS84
    return ecefToLatLngAlt(ex, ey, ez);
  }

  /**
   * 点群バッチ変換 (65k 点 / 秒を目標)
   * 事前に配列を確保して GC 圧力を最小化
   */
  transformPointCloud(
    points: { x: number; y: number; z: number }[]
  ): { lat: number; lng: number; alt: number }[] {
    const result = new Array<{ lat: number; lng: number; alt: number }>(points.length);
    for (let i = 0; i < points.length; i++) {
      result[i] = this.transformPoint(points[i].x, points[i].y, points[i].z);
    }
    return result;
  }

  /**
   * センサーローカル → ENU (East-North-Up) [m] — マウント位置原点
   * GlobalVoxelLayer でグリッドキー生成に使用
   */
  transformToENU(x: number, y: number, z: number): { e: number; n: number; u: number } {
    const [e, n, u] = _mat3MulVec(this.R_sensor, x, y, z);
    return { e, n, u };
  }

  /**
   * ENU → センサーローカル XYZ
   * GlobalVoxelRenderer でボクセル中心を Three.js 座標に戻す際に使用
   */
  enuToSensor(e: number, n: number, u: number): { x: number; y: number; z: number } {
    const [x, y, z] = _mat3TransposeMulVec(this.R_sensor, e, n, u);
    return { x, y, z };
  }

  /**
   * 逆変換: WGS84 → センサーローカル XYZ
   * GlobalVoxelRenderer でボクセル中心座標を Three.js 空間に戻す際に使用
   *
   * WGS84 → ECEF → dECEF → P_enu (R_enu2ecef^T) → P_sensor (R_sensor^T)
   */
  inverseTransformPoint(lat: number, lng: number, alt: number): { x: number; y: number; z: number } {
    // Step 1: WGS84 → ECEF
    const ecef = latLngAltToECEF(lat, lng, alt);

    // Step 2: ECEF 変位 = ECEF - ECEF_origin
    const dx = ecef[0] - this.ecef_origin[0];
    const dy = ecef[1] - this.ecef_origin[1];
    const dz = ecef[2] - this.ecef_origin[2];

    // Step 3: dECEF → P_enu (R_enu2ecef の転置 = 逆行列)
    const [e, n, u] = _mat3TransposeMulVec(this.R_enu2ecef, dx, dy, dz);

    // Step 4: P_enu → P_sensor (R_sensor の転置 = 逆行列)
    const [x, y, z] = _mat3TransposeMulVec(this.R_sensor, e, n, u);

    return { x, y, z };
  }
}

/** 3×3 行列 × ベクトル */
function _mat3MulVec(R: number[][], x: number, y: number, z: number): [number, number, number] {
  return [
    R[0][0] * x + R[0][1] * y + R[0][2] * z,
    R[1][0] * x + R[1][1] * y + R[1][2] * z,
    R[2][0] * x + R[2][1] * y + R[2][2] * z,
  ];
}

/** 3×3 行列の転置 × ベクトル (R^T × v = R の逆行列適用) */
function _mat3TransposeMulVec(R: number[][], x: number, y: number, z: number): [number, number, number] {
  return [
    R[0][0] * x + R[1][0] * y + R[2][0] * z,
    R[0][1] * x + R[1][1] * y + R[2][1] * z,
    R[0][2] * x + R[1][2] * y + R[2][2] * z,
  ];
}

/** WGS84 (lat, lng, alt) → ECEF [m] */
export function latLngAltToECEF(lat_deg: number, lng_deg: number, alt_m: number): number[] {
  const lat = (lat_deg * Math.PI) / 180;
  const lng = (lng_deg * Math.PI) / 180;
  const N = WGS84_A / Math.sqrt(1 - WGS84_E2 * Math.sin(lat) ** 2);
  const x = (N + alt_m) * Math.cos(lat) * Math.cos(lng);
  const y = (N + alt_m) * Math.cos(lat) * Math.sin(lng);
  const z = (N * (1 - WGS84_E2) + alt_m) * Math.sin(lat);
  return [x, y, z];
}

/** ECEF [m] → WGS84 (lat, lng, alt) — Heikkinen 反復法 (5回で十分収束) */
export function ecefToLatLngAlt(x: number, y: number, z: number): { lat: number; lng: number; alt: number } {
  const p = Math.sqrt(x * x + y * y);
  let lat = Math.atan2(z, p * (1 - WGS84_E2));

  for (let i = 0; i < 5; i++) {
    const N = WGS84_A / Math.sqrt(1 - WGS84_E2 * Math.sin(lat) ** 2);
    lat = Math.atan2(z + WGS84_E2 * N * Math.sin(lat), p);
  }

  const N = WGS84_A / Math.sqrt(1 - WGS84_E2 * Math.sin(lat) ** 2);
  const cosLat = Math.cos(lat);
  // 極点付近での数値安定性ガード
  const alt = Math.abs(cosLat) > 1e-10
    ? p / cosLat - N
    : Math.abs(z) - N * (1 - WGS84_E2);
  const lng = Math.atan2(y, x);

  return {
    lat: (lat * 180) / Math.PI,
    lng: (lng * 180) / Math.PI,
    alt,
  };
}

/**
 * ヘルパー関数: 点群をまとめて変換
 * (CoordinateTransformer を毎回生成したくない場合に使用)
 */
export function transformPointCloud(
  points: { x: number; y: number; z: number }[],
  mount: { position: MountPosition; orientation: MountOrientation }
): { lat: number; lng: number; alt: number }[] {
  const transformer = new CoordinateTransformer(mount);
  return transformer.transformPointCloud(points);
}
