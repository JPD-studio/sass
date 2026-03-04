import { describe, it, expect, beforeEach } from "@jest/globals";
import { VoxelGrid } from "../src/voxel-grid.js";

describe("VoxelGrid", () => {
  let grid: VoxelGrid;

  beforeEach(() => {
    grid = new VoxelGrid(1.0);
  });

  it("インスタンスを生成できる", () => {
    expect(grid).toBeDefined();
  });

  it("addPoint で点を追加できる", () => {
    grid.addPoint(0.5, 0.5, 0.5, 1);
    const snap = grid.snapshot();
    expect(snap.size).toBe(1);
  });

  it("同じボクセルに複数点を追加するとカウントが増える", () => {
    grid.addPoint(0.1, 0.2, 0.3, 1);
    grid.addPoint(0.4, 0.6, 0.8, 1);
    const snap = grid.snapshot();
    // 同じセル(0:0:0)
    expect(snap.size).toBe(1);
    expect(snap.get("0:0:0")!.count).toBe(2);
  });

  it("異なるセルの点は別エントリになる", () => {
    grid.addPoint(0.5, 0.5, 0.5, 1);
    grid.addPoint(1.5, 0.5, 0.5, 1);
    const snap = grid.snapshot();
    expect(snap.size).toBe(2);
  });

  it("snapshot() は shallow copy を返す", () => {
    grid.addPoint(0.5, 0.5, 0.5, 1);
    const snap = grid.snapshot();
    grid.addPoint(1.5, 1.5, 1.5, 2);
    // snap は変更前の状態を保持
    expect(snap.size).toBe(1);
  });

  it("clear() で全ボクセルが消える", () => {
    grid.addPoint(0.5, 0.5, 0.5, 1);
    grid.clear();
    expect(grid.snapshot().size).toBe(0);
  });

  it("keyToCenter がボクセル中心座標を返す", () => {
    grid.addPoint(2.3, 4.7, -1.5, 1);
    const snap = grid.snapshot();
    const key = [...snap.keys()][0];
    const center = grid.keyToCenter(key);
    expect(center.x).toBeCloseTo(2.5);
    expect(center.y).toBeCloseTo(4.5);
    // Math.floor(-1.5)=-2 → center = (-2+0.5)*1.0 = -1.5
    expect(center.z).toBeCloseTo(-1.5);
  });

  it("cellSize=2.0 の場合キーが正しく計算される", () => {
    const g = new VoxelGrid(2.0);
    g.addPoint(3.9, 3.9, 3.9, 1);
    const snap = g.snapshot();
    expect(snap.has("1:1:1")).toBe(true);
  });

  it("負座標でも正しくボクセル化される", () => {
    grid.addPoint(-0.5, -0.5, -0.5, 1);
    const snap = grid.snapshot();
    expect(snap.has("-1:-1:-1")).toBe(true);
  });
});
