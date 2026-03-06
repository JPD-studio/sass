import { describe, it, expect, beforeEach } from "@jest/globals";
import { BackgroundVoxelMap } from "../src/background-voxel-map.js";
import type { VoxelSnapshot } from "../src/types.js";

function makeSnapshot(entries: Record<string, number>): VoxelSnapshot {
  const snap: VoxelSnapshot = new Map();
  for (const [key, count] of Object.entries(entries)) {
    snap.set(key, { count, lastUpdated: 0 });
  }
  return snap;
}

describe("BackgroundVoxelMap", () => {
  let bg: BackgroundVoxelMap;

  beforeEach(() => {
    bg = new BackgroundVoxelMap();
  });

  it("インスタンスを生成できる", () => {
    expect(bg).toBeDefined();
  });

  it("learn 前は get が undefined を返す", () => {
    expect(bg.get("0:0:0")).toBeUndefined();
  });

  it("learn 後は stats を取得できる", () => {
    bg.learn(makeSnapshot({ "0:0:0": 5 }));
    const stats = bg.get("0:0:0");
    expect(stats).toBeDefined();
    expect(stats!.samples).toBe(1);
    expect(stats!.mean).toBe(5);
  });

  it("複数回 learn すると samples が増える", () => {
    for (let i = 0; i < 5; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 10 }));
    }
    const stats = bg.get("0:0:0");
    expect(stats!.samples).toBe(5);
  });

  it("指数移動平均で mean が収束する", () => {
    for (let i = 0; i < 100; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 10 }));
    }
    const stats = bg.get("0:0:0");
    expect(stats!.mean).toBeCloseTo(10, 0);
  });

  it("isStable は samples < minSamples のとき false", () => {
    bg.learn(makeSnapshot({ "0:0:0": 5 }));
    expect(bg.isStable(30)).toBe(false);
  });

  it("isStable は全ボクセルが minSamples 以上のとき true", () => {
    for (let i = 0; i < 30; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 5 }));
    }
    expect(bg.isStable(30)).toBe(true);
  });

  it("isStable は空のとき false", () => {
    expect(bg.isStable()).toBe(false);
  });

  it("1 つでも samples が足りないと isStable は false", () => {
    for (let i = 0; i < 30; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 5 }));
    }
    // 新しいキーは samples=1
    bg.learn(makeSnapshot({ "0:0:0": 5, "1:1:1": 3 }));
    expect(bg.isStable(30)).toBe(false);
  });
});
