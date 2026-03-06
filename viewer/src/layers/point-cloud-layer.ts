// viewer/src/layers/point-cloud-layer.ts

import type { PointData } from "../../../ws-client/src/types.js";
import type { ViewerApp } from "../index.js";
import type { RenderLayer } from "./types.js";

export class PointCloudLayer implements RenderLayer {
  readonly name = "pointcloud";
  readonly label = "点群";
  enabled = true;

  constructor(private readonly _viewer: ViewerApp) {}

  onFrame(points: PointData[], _frameId: number): void {
    this._viewer.updatePoints(points);
  }

  setVisible(visible: boolean): void {
    this._viewer.pointCloudObject.visible = visible;
  }

  dispose(): void {}
}
