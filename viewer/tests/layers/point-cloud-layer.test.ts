// viewer/tests/layers/point-cloud-layer.test.ts

import { describe, it, expect, beforeEach } from "@jest/globals";
import { PointCloudLayer } from "../../src/layers/point-cloud-layer.js";
import type { PointData } from "../../../ws-client/src/types.js";

/** ViewerApp の最小モック */
function createMockViewer() {
  return {
    updatePointsCalls: [] as PointData[][],
    updatePoints(points: PointData[]) {
      this.updatePointsCalls.push(points);
    },
    pointCloudObject: { visible: true },
  };
}

describe("PointCloudLayer", () => {
  let mockViewer: ReturnType<typeof createMockViewer>;
  let layer: PointCloudLayer;

  beforeEach(() => {
    mockViewer = createMockViewer();
    layer = new PointCloudLayer(mockViewer as any);
  });

  it("name / label / enabled の初期値が正しい", () => {
    expect(layer.name).toBe("pointcloud");
    expect(layer.label).toBe("点群");
    expect(layer.enabled).toBe(true);
  });

  it("onFrame で viewer.updatePoints() が呼ばれる", () => {
    const points: PointData[] = [{ x: 1, y: 2, z: 3 }];
    layer.onFrame(points, 1);

    expect(mockViewer.updatePointsCalls).toHaveLength(1);
    expect(mockViewer.updatePointsCalls[0]).toBe(points);
  });

  it("setVisible で pointCloudObject.visible を制御できる", () => {
    layer.setVisible(false);
    expect(mockViewer.pointCloudObject.visible).toBe(false);

    layer.setVisible(true);
    expect(mockViewer.pointCloudObject.visible).toBe(true);
  });

  it("dispose で例外が発生しない", () => {
    expect(() => layer.dispose()).not.toThrow();
  });
});
