// viewer/tests/layers/voxel-layer.test.ts

import { describe, it, expect, beforeEach } from "@jest/globals";
import { VoxelLayer } from "../../src/layers/voxel-layer.js";
import type { PointData } from "../../../ws-client/src/types.js";

/** ViewerApp の最小モック */
function createMockViewer() {
  return {
    updateVoxelsCalls: [] as { snapshot: any; cellSize: number }[],
    updateVoxels(snapshot: any, cellSize: number) {
      this.updateVoxelsCalls.push({ snapshot, cellSize });
    },
    voxelObject: { visible: true },
  };
}

describe("VoxelLayer", () => {
  let mockViewer: ReturnType<typeof createMockViewer>;
  let layer: VoxelLayer;

  beforeEach(() => {
    mockViewer = createMockViewer();
    layer = new VoxelLayer(mockViewer as any, 2.0);
  });

  it("name / label / enabled の初期値が正しい", () => {
    expect(layer.name).toBe("voxel");
    expect(layer.label).toBe("ボクセル");
    expect(layer.enabled).toBe(true);
  });

  it("onFrame で VoxelGrid にポイントを追加して updateVoxels() が呼ばれる", () => {
    const points: PointData[] = [
      { x: 1, y: 2, z: 3 },
      { x: 4, y: 5, z: 6 },
    ];
    layer.onFrame(points, 1);

    expect(mockViewer.updateVoxelsCalls).toHaveLength(1);
    const call = mockViewer.updateVoxelsCalls[0];
    expect(call.cellSize).toBe(2.0);
    // snapshot は Map（VoxelSnapshot 型）で、少なくとも 1 セルが存在するはず
    expect(call.snapshot.size).toBeGreaterThan(0);
  });

  it("onFrame を連続で呼ぶと前フレームのボクセルがクリアされる", () => {
    layer.onFrame([{ x: 0, y: 0, z: 0 }], 1);
    layer.onFrame([{ x: 100, y: 100, z: 100 }], 2);

    // 2 回呼ばれる
    expect(mockViewer.updateVoxelsCalls).toHaveLength(2);
    // 2 回目の snapshot はフレーム 1 の座標(0,0,0)のセルを含まない
    const snap2 = mockViewer.updateVoxelsCalls[1].snapshot;
    expect(snap2.size).toBe(1); // (100,100,100) の 1 セルのみ
  });

  it("setVisible で voxelObject.visible を制御できる", () => {
    layer.setVisible(false);
    expect(mockViewer.voxelObject.visible).toBe(false);

    layer.setVisible(true);
    expect(mockViewer.voxelObject.visible).toBe(true);
  });

  it("dispose で例外が発生しない", () => {
    expect(() => layer.dispose()).not.toThrow();
  });
});
