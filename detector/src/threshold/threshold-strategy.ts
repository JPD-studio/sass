export interface ThresholdStrategy {
  isIntrusion(delta: number, bgMean: number, bgStddev: number): boolean;
}
