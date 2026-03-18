export class IntrusionDetector {
    _strategy;
    constructor(_strategy) {
        this._strategy = _strategy;
    }
    evaluate(diffs) {
        const now = Date.now();
        const events = [];
        for (const diff of diffs) {
            // BackgroundStats の stddev はここでは VoxelDiffEntry に含まれないため 0 を渡す
            if (this._strategy.isIntrusion(diff.delta, diff.backgroundMean, 0)) {
                events.push({ key: diff.key, delta: diff.delta, timestamp: now });
            }
        }
        return events;
    }
    setStrategy(strategy) {
        this._strategy = strategy;
    }
}
