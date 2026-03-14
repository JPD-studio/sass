// ws-client/src/ws-connection.ts
import type {
  ConnectionConfig,
  FrameMessage,
  PointData,
  StreamOptions,
} from "./types.js";

/**
 * WebSocket 接続管理クラス。
 * - コールバック方式（onMessage）: viewer 向け
 * - AsyncIterator 方式（frames()）: detector ヘッドレス向け
 * - 切断時に自動再接続（reconnectInterval ms 後）
 */
export class WsConnection {
  private socket: any = null;
  private _connected = false;
  private _stopped = false;
  private _callbacks: Array<(points: PointData[]) => void> = [];
  private _frameQueue: PointData[][] = [];
  private _frameResolvers: Array<(value: IteratorResult<PointData[]>) => void> = [];
  private _retryCount = 0;

  constructor(private readonly config: ConnectionConfig) {}

  /** WebSocket 接続を開始する。切断時は自動再接続する。 */
  connect(): void {
    this._stopped = false;
    this._initAndConnect();
  }

  private async _initAndConnect(): Promise<void> {
    // WebSocket実装を取得
    let WebSocketImpl: any;

    if (typeof globalThis !== "undefined" && (globalThis as any).WebSocket) {
      WebSocketImpl = (globalThis as any).WebSocket;
    } else {
      // Node.js環境: wsパッケージを使用
      try {
        const wsModule = await import("ws");
        WebSocketImpl = wsModule.WebSocket || wsModule.default;
      } catch (e) {
        console.error("[WsConnection] Failed to load WebSocket:", e);
        this._scheduleReconnect();
        return;
      }
    }

    this._doConnect(WebSocketImpl);
  }

  /** 接続を閉じ、再接続を停止する。 */
  disconnect(): void {
    this._stopped = true;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this._connected = false;
    // 待機中の AsyncIterator を終了させる
    for (const resolve of this._frameResolvers) {
      resolve({ value: undefined as unknown as PointData[], done: true });
    }
    this._frameResolvers = [];
  }

  /** 接続中かどうか */
  isConnected(): boolean {
    return this._connected;
  }

  /**
   * コールバック方式でメッセージを受信する（viewer 向け）。
   * connect() より前に登録しておくこと。
   */
  onMessage(callback: (points: PointData[]) => void): void {
    this._callbacks.push(callback);
  }

  /**
   * AsyncIterator 方式でフレームを逐次受信する（detector ヘッドレス向け）。
   * connect() が呼ばれていること。
   */
  async *frames(options?: StreamOptions): AsyncGenerator<PointData[]> {
    let count = 0;
    const maxFrames = options?.maxFrames;
    while (!this._stopped) {
      if (this._frameQueue.length > 0) {
        const frame = this._frameQueue.shift()!;
        yield frame;
        count++;
        if (maxFrames !== undefined && count >= maxFrames) return;
      } else {
        // キューが空なら次のフレームを待つ
        const next = await new Promise<IteratorResult<PointData[]>>((resolve) => {
          this._frameResolvers.push(resolve);
        });
        if (next.done) return;
        yield next.value;
        count++;
        if (maxFrames !== undefined && count >= maxFrames) return;
      }
    }
  }

  // ------------------------------------------------------------------ //
  // 内部ヘルパー                                                          //
  // ------------------------------------------------------------------ //

  private _doConnect(WebSocketImpl: any): void {
    if (this._stopped) return;
    console.log(
      `[WsConnection._doConnect] Attempting to connect to ${this.config.url}`
    );

    if (!WebSocketImpl) {
      console.error(
        `[WsConnection._doConnect] WebSocket implementation not available`
      );
      this._scheduleReconnect();
      return;
    }

    try {
      this.socket = new WebSocketImpl(this.config.url) as any;
      console.log(`[WsConnection._doConnect] WebSocket object created`);
    } catch (err) {
      console.log(
        `[WsConnection._doConnect] Failed to create WebSocket:`,
        err
      );
      this._scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this._connected = true;
      this._retryCount = 0;
      console.log(`[WsConnection] Connected to ${this.config.url}`);
    };

    this.socket.onmessage = (event: any) => {
      const data = typeof event.data === "string" ? event.data : event.data.toString();
      const points = this._parseMessage(data);
      if (points === null) return;

      // コールバック方式
      for (const cb of this._callbacks) cb(points);

      // AsyncIterator 方式
      if (this._frameResolvers.length > 0) {
        const resolve = this._frameResolvers.shift()!;
        resolve({ value: points, done: false });
      } else {
        this._frameQueue.push(points);
      }
    };

    this.socket.onclose = () => {
      this._connected = false;
      this.socket = null;
      console.log(`[WsConnection] Disconnected from ${this.config.url}`);
      this._scheduleReconnect();
    };

    this.socket.onerror = (event: any) => {
      console.log(
        `[WsConnection] Error connecting to ${this.config.url}:`,
        event
      );
      // onclose が後続するので再接続はそちらに任せる
    };
  }

  private _scheduleReconnect(): void {
    if (this._stopped) return;
    const maxRetries = this.config.maxRetries;
    if (maxRetries !== undefined && this._retryCount >= maxRetries) return;

    const interval = this.config.reconnectInterval ?? 3000;
    this._retryCount++;
    setTimeout(() => this._initAndConnect(), interval);
  }

  private _parseMessage(data: string): PointData[] | null {
    try {
      const msg = JSON.parse(data) as FrameMessage;
      const { x, y, z, intensity } = msg.points;
      return x.map((xi, i) => ({
        x: xi,
        y: y[i],
        z: z[i],
        intensity: intensity?.[i],
        timestamp: msg.timestamp,
      }));
    } catch {
      return null;
    }
  }
}
