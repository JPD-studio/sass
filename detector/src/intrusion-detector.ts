import type { VoxelDiffEntry } from "../../voxel/src/types.js";
import type { ThresholdStrategy } from "./threshold/threshold-strategy.js";
import type { IntrusionEvent } from "./types.js";

export class IntrusionDetector {
  constructor(private _strategy: ThresholdStrategy) {}

  evaluate(diffs: VoxelDiffEntry[]): IntrusionEvent[] {
    const now = Date.now();
    const events: IntrusionEvent[] = [];
    for (const diff of diffs) {
      // BackgroundStats の stddev はここでは VoxelDiffEntry に含まれないため 0 を渡す
      if (this._strategy.isIntrusion(diff.delta, diff.backgroundMean, 0)) {
        events.push({ key: diff.key, delta: diff.delta, timestamp: now });
      }
    }
    return events;
  }

  setStrategy(strategy: ThresholdStrategy): void {
    this._strategy = strategy;
  }
}
