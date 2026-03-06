export class Stats {
  private _fps = 0;
  private _lastTime = performance.now();
  private _frames = 0;

  update(): void {
    this._frames++;
    const now = performance.now();
    const elapsed = now - this._lastTime;
    if (elapsed >= 1000) {
      this._fps = (this._frames * 1000) / elapsed;
      this._frames = 0;
      this._lastTime = now;
    }
  }

  get fps(): number {
    return this._fps;
  }
}
