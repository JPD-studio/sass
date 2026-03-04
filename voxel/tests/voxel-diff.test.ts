import { describe, it, expect } from "@jest/globals";
import { computeDiff } from "../src/voxel-diff.js";
import { BackgroundVoxelMap } from "../src/background-voxel-map.js";
import type { VoxelSnapshot } from "../src/types.js";

function makeSnapshot(entries: Record<string, number>): VoxelSnapshot {
  const snap: VoxelSnapshot = new Map();
  for (const [key, count] of Object.entries(entries)) {
    snap.set(key, { count, lastUpdated: 0 });
  }
  return snap;
}

describe("computeDiff", () => {
  it("背景未学習のボクセルは delta=count で返る", () => {
    const bg = new BackgroundVoxelMap();
    const current = makeSnapshot({ "0:0:0": 5 });
    const diffs = computeDiff(current, bg);
    expect(diffs.length).toBe(1);
    expect(diffs[0].delta).toBe(5);
    expect(diffs[0].currentCount).toBe(5);
    expect(diffs[0].backgroundMean).toBe(0);
  });

  it("delta <= 0 のエントリは返らない", () => {
    const bg = new BackgroundVoxelMap();
    // 十分に学習して mean を高くする
    for (let i = 0; i < 100; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 10 }));
    }
    const current = makeSnapshot({ "0:0:0": 3 });
    const diffs = computeDiff(current, bg);
    expect(diffs.length).toBe(0);
  });

  it("delta > 0 のみ返す（複数ボクセル）", () => {
    const bg = new BackgroundVoxelMap();
    for (let i = 0; i < 100; i++) {
      bg.learn(makeSnapshot({ "0:0:0": 5, "1:1:1": 5 }));
    }
    // "0:0:0" は delta>0, "1:1:1" は delta<=0
    const current = makeSnapshot({ "0:0:0": 10, "1:1:1": 3 });
    const diffs = computeDiff(current, bg);
    expect(diffs.length).toBe(1);
    expect(diffs[0].key).toBe("0:0:0");
    expect(diffs[0].delta).toBeGreaterThan(0);
  });

  it("current が空のとき空配列を返す", () => {
    const bg = new BackgroundVoxelMap();
    const diffs = computeDiff(new Map(), bg);
    expect(diffs).toEqual([]);
  });

  it("VoxelDiffEntry のフィールドが揃っている", () => {
    const bg = new BackgroundVoxelMap();
    const current = makeSnapshot({ "2:3:4": 7 });
    const diffs = computeDiff(current, bg);
    expect(diffs[0]).toHaveProperty("key");
    expect(diffs[0]).toHaveProperty("currentCount");
    expect(diffs[0]).toHaveProperty("backgroundMean");
    expect(diffs[0]).toHaveProperty("delta");
  });
});
