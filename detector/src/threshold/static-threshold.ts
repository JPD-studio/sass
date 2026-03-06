import type { ThresholdStrategy } from "./threshold-strategy.js";

export class StaticThreshold implements ThresholdStrategy {
  constructor(private readonly threshold: number) {}

  isIntrusion(delta: number, _bgMean: number, _bgStddev: number): boolean {
    return delta > this.threshold;
  }
}
