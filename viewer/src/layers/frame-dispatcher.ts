// viewer/src/layers/frame-dispatcher.ts

import type { PointData } from "../../../ws-client/src/types.js";
import type { RenderLayer } from "./types.js";

export class FrameDispatcher {
  private _layers: RenderLayer[] = [];
  private _frameId = 0;

  register(layer: RenderLayer): void {
    this._layers.push(layer);
  }

  unregister(name: string): void {
    const layer = this._layers.find((l) => l.name === name);
    if (layer) layer.dispose();
    this._layers = this._layers.filter((l) => l.name !== name);
  }

  /** WsConnection.onMessage() から呼ぶ */
  dispatch(points: PointData[]): void {
    this._frameId++;
    for (const layer of this._layers) {
      if (layer.enabled) {
        try {
          layer.onFrame(points, this._frameId);
        } catch (e) {
          console.error(`[FrameDispatcher] ${layer.name} onFrame failed:`, e);
        }
      }
    }
  }

  /** レイヤーの enabled 切り替え + Three.js visible 連動 */
  toggle(name: string): void {
    const layer = this._layers.find((l) => l.name === name);
    if (layer) {
      layer.enabled = !layer.enabled;
      layer.setVisible(layer.enabled);
    }
  }

  get frameId(): number {
    return this._frameId;
  }
  get layers(): readonly RenderLayer[] {
    return this._layers;
  }
}
