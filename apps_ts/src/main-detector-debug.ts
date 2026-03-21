/**
 * main-detector-debug.ts
 * デバッグ版: WebSocket接続状況とデータフローを詳細に出力する
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { resolveWsUrl } from "../../ws-client/src/resolve-ws-url-node.js";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(readFileSync(join(__dirname, "../../config/sass.json"), "utf-8"));

console.log("[DEBUG] Config loaded:", config);

const wsUrl = resolveWsUrl(join(__dirname, "../../config/websocket.json"));
const conn = new WsConnection({
  url: wsUrl,
  reconnectInterval: 3000,
});

console.log(`[DEBUG] WsConnection created with ${wsUrl}, starting connection...`);
conn.connect();

// 接続状態を定期的にチェック
const statusInterval = setInterval(() => {
  console.log(`[DEBUG] Connected: ${conn.isConnected()}`);
}, 1000);

// データ受信テスト
(async () => {
  console.log("[DEBUG] Starting frame iteration...");
  let frameCount = 0;
  for await (const points of conn.frames()) {
    frameCount++;
    console.log(
      `[DEBUG] Received frame ${frameCount}: ${points.length} points`
    );
    if (frameCount >= 5) {
      console.log("[DEBUG] Received 5 frames, exiting...");
      break;
    }
  }
  console.log("[DEBUG] Frame iteration ended");
  clearInterval(statusInterval);
  process.exit(0);
})().catch((err) => {
  console.error("[ERROR] Fatal error:", err);
  clearInterval(statusInterval);
  process.exit(1);
});

// 30秒でタイムアウト
setTimeout(() => {
  console.log("[TIMEOUT] No data received within 30 seconds");
  clearInterval(statusInterval);
  process.exit(1);
}, 30000);
