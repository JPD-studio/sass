/**
 * euler-quaternion.ts
 * Euler 角 ↔ Quaternion 変換ユーティリティ
 *
 * 座標系規約 (航法規約):
 *   センサーローカル: x = 前方、y = 左方、z = 上方
 *   ENU: x = East、y = North、z = Up
 *   heading: 0° = 真北、時計回り正
 *   pitch: 0° = 水平、正 = 上向き
 *   roll: 0° = 水平、正 = 右傾き
 *
 * eulerToQuaternion は以下の回転行列を生成する:
 *   R = Rz(90° - heading) × Ry(-pitch) × Rx(roll)
 *
 * 検証:
 *   heading=0:  Rz(90°) → [100,0,0] → [0,100,0] = 北に100m ✓
 *   heading=90: Rz(0°)  → [100,0,0] → [100,0,0] = 東に100m ✓
 *
 * cepf_sdk/utils/quaternion.py の TS 版
 */

export interface Quaternion {
  w: number;
  x: number;
  y: number;
  z: number;
}

/**
 * Euler 角 → Quaternion (ZYX 順序)
 * 内部で (90° - heading) を適用し、センサー x=前方 → ENU 北 へ変換
 */
export function eulerToQuaternion(
  heading_deg: number,
  pitch_deg: number,
  roll_deg: number
): Quaternion {
  // 航法規約: heading=0°=北、時計回り正
  // センサー x=前方 が ENU y=North に一致するよう (90°-heading) を Z 回転に適用
  const rz = ((90.0 - heading_deg) * Math.PI) / 180.0;
  const ry = (-pitch_deg * Math.PI) / 180.0;
  const rx = (roll_deg * Math.PI) / 180.0;

  const cr = Math.cos(rx / 2);
  const sr = Math.sin(rx / 2);
  const cp = Math.cos(ry / 2);
  const sp = Math.sin(ry / 2);
  const cy = Math.cos(rz / 2);
  const sy = Math.sin(rz / 2);

  // ZYX 順序: q = q_z ⊗ q_y ⊗ q_x
  return {
    w: cy * cp * cr + sy * sp * sr,
    x: cy * cp * sr - sy * sp * cr,
    y: cy * sp * cr + sy * cp * sr,
    z: sy * cp * cr - cy * sp * sr,
  };
}

/**
 * Quaternion → Euler 角 (ZYX 順序の逆変換)
 */
export function quaternionToEuler(q: Quaternion): {
  heading_deg: number;
  pitch_deg: number;
  roll_deg: number;
} {
  const { w, x, y, z } = q;

  // Roll (X 軸回転)
  const sinr_cosp = 2 * (w * x + y * z);
  const cosr_cosp = 1 - 2 * (x * x + y * y);
  const roll_rad = Math.atan2(sinr_cosp, cosr_cosp);

  // Pitch (Y 軸回転) - ジンバルロック対策
  const sinp = 2 * (w * y - z * x);
  const pitch_rad = Math.abs(sinp) >= 1
    ? (Math.PI / 2) * Math.sign(sinp)
    : Math.asin(sinp);

  // Yaw (Z 軸回転)
  const siny_cosp = 2 * (w * z + x * y);
  const cosy_cosp = 1 - 2 * (y * y + z * z);
  const rz = Math.atan2(siny_cosp, cosy_cosp);

  // (90° - heading) の逆変換
  const heading_rad = (Math.PI / 2) - rz;

  return {
    heading_deg: (heading_rad * 180) / Math.PI,
    pitch_deg: (-pitch_rad * 180) / Math.PI,
    roll_deg: (roll_rad * 180) / Math.PI,
  };
}

/**
 * Quaternion → 3×3 回転行列
 * cepf_sdk/utils/quaternion.py の quaternion_to_rotation_matrix() の TS 版
 * 入力: {w, x, y, z}、出力: 3×3 number[][]
 */
export function quaternionToRotationMatrix(q: Quaternion): number[][] {
  const { w, x, y, z } = q;
  return [
    [1 - 2 * (y * y + z * z),     2 * (x * y - w * z),     2 * (x * z + w * y)],
    [    2 * (x * y + w * z), 1 - 2 * (x * x + z * z),     2 * (y * z - w * x)],
    [    2 * (x * z - w * y),     2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
  ];
}
