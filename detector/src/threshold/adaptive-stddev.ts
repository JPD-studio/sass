import type { ThresholdStrategy } from "./threshold-strategy.js";

export class AdaptiveStddevThreshold implements ThresholdStrategy {
  constructor(private readonly sigma: number = 2.0) {}

  isIntrusion(delta: number, _bgMean: number, bgStddev: number): boolean {
    if (bgStddev === 0) return delta > 0;
    return delta > this.sigma * bgStddev;
  }
}
