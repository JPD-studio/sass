const ALPHA = 0.1;
export class BackgroundVoxelMap {
    _stats = new Map();
    learn(snapshot) {
        for (const [key, state] of snapshot) {
            const count = state.count;
            const existing = this._stats.get(key);
            if (!existing) {
                this._stats.set(key, { mean: count, stddev: 0, samples: 1 });
            }
            else {
                const delta = count - existing.mean;
                existing.mean += ALPHA * delta;
                existing.stddev += ALPHA * (Math.abs(delta) - existing.stddev);
                existing.samples += 1;
            }
        }
    }
    get(key) {
        return this._stats.get(key);
    }
    isStable(minSamples = 30) {
        if (this._stats.size === 0)
            return false;
        for (const stats of this._stats.values()) {
            if (stats.samples < minSamples)
                return false;
        }
        return true;
    }
}
