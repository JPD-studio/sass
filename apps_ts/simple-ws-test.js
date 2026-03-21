/**
 * simple-ws-test.ts
 * 直接wsパッケージを使ってWebSocket接続をテスト
 */
import WebSocket from "ws";
const url = "ws://127.0.0.1:8765";
const ws = new WebSocket(url);
console.log("[TEST] Attempting to connect to", url);
ws.on("open", () => {
    console.log("[TEST] Connected successfully!");
});
ws.on("message", (data) => {
    const msg = typeof data === "string" ? data : data.toString();
    try {
        const parsed = JSON.parse(msg);
        console.log(`[TEST] Received frame ${parsed.frame_id}: ${parsed.points.x.length} points`);
    }
    catch {
        console.log("[TEST] Received data:", msg.substring(0, 100));
    }
});
ws.on("error", (error) => {
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
