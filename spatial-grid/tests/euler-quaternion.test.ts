import { describe, test, expect } from "@jest/globals";
import {
  eulerToQuaternion,
  quaternionToEuler,
  quaternionToRotationMatrix,
} from "../src/euler-quaternion.js";

const EPS = 1e-9;
const DEG_EPS = 1e-6;

describe("eulerToQuaternion", () => {
  test("identity: heading=0, pitch=0, roll=0 → Rz(90°)", () => {
    const q = eulerToQuaternion(0, 0, 0);
    // heading=0 → rz=90° → q = (cos45°, 0, 0, sin45°)
    const s = Math.SQRT2 / 2;
    expect(q.w).toBeCloseTo(s, 10);
    expect(q.x).toBeCloseTo(0, 10);
    expect(q.y).toBeCloseTo(0, 10);
    expect(q.z).toBeCloseTo(s, 10);
  });

  test("heading=90 → rz=0° → identity quaternion", () => {
    const q = eulerToQuaternion(90, 0, 0);
    expect(q.w).toBeCloseTo(1, 10);
    expect(q.x).toBeCloseTo(0, 10);
    expect(q.y).toBeCloseTo(0, 10);
    expect(q.z).toBeCloseTo(0, 10);
  });

  test("quaternion norm = 1 (all angles)", () => {
    const cases = [
      [0, 0, 0], [45, 10, 5], [90, 0, 0],
      [180, -30, 15], [270, 0, 0], [-45, 5, -10],
    ];
    for (const [h, p, r] of cases) {
      const q = eulerToQuaternion(h, p, r);
      const norm = Math.sqrt(q.w ** 2 + q.x ** 2 + q.y ** 2 + q.z ** 2);
      expect(norm).toBeCloseTo(1.0, 10);
    }
  });
});

describe("quaternionToRotationMatrix", () => {
  test("heading=0 → 前方(100,0,0) が 北(0,100,0) に写る", () => {
    const q = eulerToQuaternion(0, 0, 0);
    const R = quaternionToRotationMatrix(q);
    // R × [100, 0, 0]
    const e = R[0][0] * 100;
    const n = R[1][0] * 100;
    const u = R[2][0] * 100;
    expect(e).toBeCloseTo(0, 6);
    expect(n).toBeCloseTo(100, 6);
    expect(u).toBeCloseTo(0, 6);
  });

  test("heading=90 → 前方(100,0,0) が 東(100,0,0) に写る", () => {
    const q = eulerToQuaternion(90, 0, 0);
    const R = quaternionToRotationMatrix(q);
    const e = R[0][0] * 100;
    const n = R[1][0] * 100;
    const u = R[2][0] * 100;
    expect(e).toBeCloseTo(100, 6);
    expect(n).toBeCloseTo(0, 6);
    expect(u).toBeCloseTo(0, 6);
  });

  test("heading=180 → 前方が 南方向 に写る", () => {
    const q = eulerToQuaternion(180, 0, 0);
    const R = quaternionToRotationMatrix(q);
    const e = R[0][0] * 100;
    const n = R[1][0] * 100;
    const u = R[2][0] * 100;
    expect(e).toBeCloseTo(0, 6);
    expect(n).toBeCloseTo(-100, 6);
    expect(u).toBeCloseTo(0, 6);
  });

  test("heading=270 → 前方が 西方向 に写る", () => {
    const q = eulerToQuaternion(270, 0, 0);
    const R = quaternionToRotationMatrix(q);
    const e = R[0][0] * 100;
    const n = R[1][0] * 100;
    const u = R[2][0] * 100;
    expect(e).toBeCloseTo(-100, 6);
    expect(n).toBeCloseTo(0, 6);
    expect(u).toBeCloseTo(0, 6);
  });

  test("回転行列は直交行列 (R × Rᵀ = I)", () => {
    const q = eulerToQuaternion(45, 10, 5);
    const R = quaternionToRotationMatrix(q);
    // R × Rᵀ = I を検証
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        let dot = 0;
        for (let k = 0; k < 3; k++) dot += R[i][k] * R[j][k];
        expect(dot).toBeCloseTo(i === j ? 1 : 0, 10);
      }
    }
  });
});

describe("quaternionToEuler (往復変換)", () => {
  test("heading=0, pitch=0, roll=0 の往復", () => {
    const q = eulerToQuaternion(0, 0, 0);
    const euler = quaternionToEuler(q);
    expect(euler.heading_deg).toBeCloseTo(0, 4);
    expect(euler.pitch_deg).toBeCloseTo(0, 4);
    expect(euler.roll_deg).toBeCloseTo(0, 4);
  });

  test("heading=45, pitch=10, roll=5 の往復", () => {
    const q = eulerToQuaternion(45, 10, 5);
    const euler = quaternionToEuler(q);
    expect(euler.heading_deg).toBeCloseTo(45, 4);
    expect(euler.pitch_deg).toBeCloseTo(10, 4);
    expect(euler.roll_deg).toBeCloseTo(5, 4);
  });

  test("heading=90, pitch=0, roll=0 の往復", () => {
    const q = eulerToQuaternion(90, 0, 0);
    const euler = quaternionToEuler(q);
    expect(euler.heading_deg).toBeCloseTo(90, 4);
    expect(euler.pitch_deg).toBeCloseTo(0, 4);
    expect(euler.roll_deg).toBeCloseTo(0, 4);
  });
});
