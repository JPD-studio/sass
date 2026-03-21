// ws-client/src/resolve-ws-url-node.ts
/**
 * Node.js 環境用 WebSocket URL 解決。
 * runtime/websocket.json から読み込み、なければデフォルト値を返す。
 */
import { readFileSync, existsSync } from "fs";

export function resolveWsUrl(runtimeJsonPath?: string): string {
  if (runtimeJsonPath && existsSync(runtimeJsonPath)) {
    try {
      const data = JSON.parse(readFileSync(runtimeJsonPath, "utf-8"));
      if (data.websocket_url) return data.websocket_url;
    } catch { /* fallback */ }
  }
  return "ws://127.0.0.1:8765";
}
