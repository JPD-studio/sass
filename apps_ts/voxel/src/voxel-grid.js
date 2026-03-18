export class VoxelGrid {
    cellSize;
    _cells = new Map();
    constructor(cellSize = 1.0) {
        this.cellSize = cellSize;
    }
    addPoint(x, y, z, frameId) {
        const key = `${Math.floor(x / this.cellSize)}:${Math.floor(y / this.cellSize)}:${Math.floor(z / this.cellSize)}`;
        const existing = this._cells.get(key);
        if (existing) {
            existing.count += 1;
            existing.lastUpdated = frameId;
        }
        else {
            this._cells.set(key, { count: 1, lastUpdated: frameId });
        }
    }
    snapshot() {
        return new Map(this._cells);
    }
    clear() {
        this._cells.clear();
    }
    keyToCenter(key) {
        const parts = key.split(":").map(Number);
        return {
            x: (parts[0] + 0.5) * this.cellSize,
            y: (parts[1] + 0.5) * this.cellSize,
            z: (parts[2] + 0.5) * this.cellSize,
        };
    }
}
