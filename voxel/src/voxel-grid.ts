import type { VoxelKey, VoxelSnapshot, VoxelState } from "./types.js";

export class VoxelGrid {
  private _cells = new Map<VoxelKey, VoxelState>();

  constructor(private readonly cellSize: number = 1.0) {}

  addPoint(x: number, y: number, z: number, frameId: number): void {
    const key: VoxelKey = `${Math.floor(x / this.cellSize)}:${Math.floor(y / this.cellSize)}:${Math.floor(z / this.cellSize)}`;
    const existing = this._cells.get(key);
    if (existing) {
      existing.count += 1;
      existing.lastUpdated = frameId;
    } else {
      this._cells.set(key, { count: 1, lastUpdated: frameId });
    }
  }

  snapshot(): VoxelSnapshot {
    return new Map(this._cells);
  }

  clear(): void {
    this._cells.clear();
  }

  keyToCenter(key: VoxelKey): { x: number; y: number; z: number } {
    const parts = key.split(":").map(Number);
    return {
      x: (parts[0] + 0.5) * this.cellSize,
      y: (parts[1] + 0.5) * this.cellSize,
      z: (parts[2] + 0.5) * this.cellSize,
    };
  }
}
