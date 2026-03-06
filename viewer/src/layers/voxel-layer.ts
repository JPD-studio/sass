// viewer/src/layers/voxel-layer.ts

import type { PointData } from "../../../ws-client/src/types.js";
import { VoxelGrid } from "../../../voxel/src/voxel-grid.js";
import type { ViewerApp } from "../index.js";
import type { RenderLayer } from "./types.js";

export class VoxelLayer implements RenderLayer {
  readonly name = "voxel";
  readonly label = "ボクセル";
  enabled = true;

  private _grid: VoxelGrid;
  private _cellSize: number;

  constructor(
    private readonly _viewer: ViewerApp,
    cellSize: number = 1.0,
  ) {
    this._grid = new VoxelGrid(cellSize);
    this._cellSize = cellSize;
  }

  onFrame(points: PointData[], frameId: number): void {
    this._grid.clear();
    for (const p of points) {
      this._grid.addPoint(p.x, p.y, -p.z, frameId); // センサーフレームの Z は下向き → 反転
    }
    this._viewer.updateVoxels(this._grid.snapshot(), this._cellSize);
  }

  setVisible(visible: boolean): void {
    this._viewer.voxelObject.visible = visible;
  }

  dispose(): void {
    this._grid.clear();
  }
}
