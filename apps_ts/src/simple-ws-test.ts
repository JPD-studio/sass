/**
 * simple-ws-test.ts
 * 直接wsパッケージを使ってWebSocket接続をテスト
 */
import WebSocket from "ws";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { resolveWsUrl } from "../../ws-client/src/resolve-ws-url-node.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const url = resolveWsUrl(join(__dirname, "../../config/websocket.json"));

const ws = new WebSocket(url);

console.log("[TEST] Attempting to connect to", url);

ws.on("open", () => {
  console.log("[TEST] Connected successfully!");
});

ws.on("message", (data: any) => {
  const msg = typeof data === "string" ? data : data.toString();
  try {
    const parsed = JSON.parse(msg);
    console.log(
      `[TEST] Received frame ${parsed.frame_id}: ${parsed.points.x.length} points`
    );
  } catch {
    console.log("[TEST] Received data:", msg.substring(0, 100));
  }
});

ws.on("error", (error: any) => {
  console.error("[TEST] WebSocket error:", error.message || error);
});

ws.on("close", () => {
  console.log("[TEST] Connection closed");
});

// 5秒でタイムアウト
setTimeout(() => {
  console.log("[TEST] Timeout - exiting");
  ws.close();
  process.exit(0);
}, 5000);
