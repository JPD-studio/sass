import type { ThresholdStrategy } from "./threshold-strategy.js";

export class AdaptiveMeanThreshold implements ThresholdStrategy {
  constructor(private readonly multiplier: number = 2.0) {}

  isIntrusion(delta: number, bgMean: number, _bgStddev: number): boolean {
    return delta > bgMean * this.multiplier;
  }
}
