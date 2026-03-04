// ws-client/src/types.ts
/** WebSocket 接続設定 */
export interface ConnectionConfig {
  /** WebSocket URL。例: "ws://192.168.1.100:8765" */
  url: string;
  /** 自動再接続間隔 ms（デフォルト 3000） */
  reconnectInterval?: number;
  /** 最大再試行回数（デフォルト: undefined = 無限） */
  maxRetries?: number;
}

/** 点群の 1 点分のデータ */
export interface PointData {
  x: number;
  y: number;
  z: number;
  intensity?: number;
  timestamp?: number;
}

/** frames() に渡すオプション */
export interface StreamOptions {
  /** 取得フレーム上限（undefined = 無限） */
  maxFrames?: number;
}

/** Python 側から送信される JSON の形式 */
export interface FrameMessage {
  frame_id: number;
  timestamp: number;
  points: {
    x: number[];
    y: number[];
    z: number[];
    intensity?: number[];
  };
}
