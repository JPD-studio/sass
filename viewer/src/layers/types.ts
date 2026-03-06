// viewer/src/layers/types.ts

import type { PointData } from "../../../ws-client/src/types.js";

export interface RenderLayer {
  /** レイヤー名（UI 表示・デバッグ用） */
  readonly name: string;

  /** 日本語の表示ラベル */
  readonly label: string;

  /** レイヤーの表示 ON/OFF */
  enabled: boolean;

  /**
   * フレーム受信時に FrameDispatcher から呼ばれる。
   * 静的レイヤー（ワイヤーフレーム等）では no-op。
   */
  onFrame(points: PointData[], frameId: number): void;

  /** Three.js オブジェクトの visible を enabled に連動させる */
  setVisible(visible: boolean): void;

  /** レイヤー破棄時のクリーンアップ */
  dispose(): void;
}
