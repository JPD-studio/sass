// ws-client/src/ws-connection-node.ts
/**
 * Node.js環境用WebSocket接続クラス
 */
import WebSocket from "ws";
export class WsConnection {
    constructor(config) {
        this.config = config;
        this.socket = null;
        this._connected = false;
        this._stopped = false;
        this._callbacks = [];
        this._frameQueue = [];
        this._frameResolvers = [];
        this._retryCount = 0;
    }
    connect() {
        this._stopped = false;
        this._doConnect();
    }
    disconnect() {
        this._stopped = true;
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        this._connected = false;
        for (const resolve of this._frameResolvers) {
            resolve({ value: undefined, done: true });
        }
        this._frameResolvers = [];
    }
    isConnected() {
        return this._connected;
    }
    onMessage(callback) {
        this._callbacks.push(callback);
    }
    async *frames(options) {
        let count = 0;
        const maxFrames = options?.maxFrames;
        while (!this._stopped) {
            if (this._frameQueue.length > 0) {
                const frame = this._frameQueue.shift();
                yield frame;
                count++;
                if (maxFrames !== undefined && count >= maxFrames)
                    return;
            }
            else {
                const next = await new Promise((resolve) => {
                    this._frameResolvers.push(resolve);
                });
                if (next.done)
                    return;
                yield next.value;
                count++;
                if (maxFrames !== undefined && count >= maxFrames)
                    return;
            }
        }
    }
    _doConnect() {
        if (this._stopped)
            return;
        console.log(`[WsConnection] Connecting to ${this.config.url}`);
        try {
            this.socket = new WebSocket(this.config.url);
        }
        catch (err) {
            console.error(`[WsConnection] Failed to create WebSocket:`, err);
            this._scheduleReconnect();
            return;
        }
        this.socket.on("open", () => {
            this._connected = true;
            this._retryCount = 0;
            console.log(`[WsConnection] Connected to ${this.config.url}`);
        });
        this.socket.on("message", (data) => {
            const message = typeof data === "string" ? data : data.toString();
            const points = this._parseMessage(message);
            if (points === null)
                return;
            for (const cb of this._callbacks)
                cb(points);
            if (this._frameResolvers.length > 0) {
                const resolve = this._frameResolvers.shift();
                resolve({ value: points, done: false });
            }
            else {
                this._frameQueue.push(points);
            }
        });
        this.socket.on("close", () => {
            this._connected = false;
            this.socket = null;
            console.log(`[WsConnection] Disconnected`);
            this._scheduleReconnect();
        });
        this.socket.on("error", (err) => {
            console.error(`[WsConnection] Error:`, err.message || err);
        });
    }
    _scheduleReconnect() {
        if (this._stopped)
            return;
        const maxRetries = this.config.maxRetries;
        if (maxRetries !== undefined && this._retryCount >= maxRetries)
            return;
        const interval = this.config.reconnectInterval ?? 3000;
        this._retryCount++;
        console.log(`[WsConnection] Reconnecting in ${interval}ms (attempt ${this._retryCount})`);
        setTimeout(() => this._doConnect(), interval);
    }
    _parseMessage(data) {
        try {
            const msg = JSON.parse(data);
            const { x, y, z, intensity } = msg.points;
            return x.map((xi, i) => ({
                x: xi,
                y: y[i],
                z: z[i],
                intensity: intensity?.[i],
                timestamp: msg.timestamp,
            }));
        }
        catch {
            return null;
        }
    }
}
