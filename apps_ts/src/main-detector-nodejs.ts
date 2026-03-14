/**
 * main-detector-nodejs.ts
 * Node.js環境用の侵入検知エントリーポイント
 * wsパッケージを直接使用してWebSocket接続のみを実現
 */
import * as WebSocketModule from "ws";
// @ts-ignore
const WebSocket = WebSocketModule.WebSocket || WebSocketModule.default;
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { VoxelGrid } from "../../voxel/src/voxel-grid.js";
import { BackgroundVoxelMap } from "../../voxel/src/background-voxel-map.js";
import { computeDiff } from "../../voxel/src/voxel-diff.js";
import { IntrusionDetector } from "../../detector/src/intrusion-detector.js";
import { AdaptiveStddevThreshold } from "../../detector/src/threshold/adaptive-stddev.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sensorsPath = path.join(__dirname, "../sensors.json");
const sensorsFallbackPath = path.join(__dirname, "../sensors.example.json");

// configを読み込む
let config: any;
try {
  const content = fs.readFileSync(
    fs.existsSync(sensorsPath) ? sensorsPath : sensorsFallbackPath,
    "utf-8"
  );
  config = JSON.parse(content);
  console.log("[DETECTOR] Config loaded:", config.websocket_url);
} catch (err) {
  console.error("[DETECTOR] Failed to load config:", err);
  process.exit(1);
}

// グローバル設定
const grid = new VoxelGrid(config.voxel_cell_size);
const bgMap = new BackgroundVoxelMap();
const strategy = new AdaptiveStddevThreshold(config.detector.sigma);
const detector = new IntrusionDetector(strategy);
const minSamples = config.detector.min_background_samples;
let frameId = 0;
let connectedTime = Date.now();

// WebSocket接続
const ws = new WebSocket(config.websocket_url);

ws.on("open", () => {
  console.log("[DETECTOR] Connected to", config.websocket_url);
  connectedTime = Date.now();
});

ws.on("message", (data: any) => {
  try {
    const message = typeof data === "string" ? data : data.toString();
    const frame = JSON.parse(message);
    
    if (!frame.points || !frame.points.x) {
      return;
    }

    // フレームデータを処理
    const points = frame.points;
    grid.clear();
    
    for (let i = 0; i < points.x.length; i++) {
      grid.addPoint(points.x[i], points.y[i], points.z[i], frameId);
    }
    frameId++;

    // 背景学習
    const snapshot = grid.snapshot();
    bgMap.learn(snapshot);

    // 安定性チェック
    if (!bgMap.isStable(minSamples)) {
      if (frameId % 50 === 0) {
        console.log(`[DETECTOR] Learning... frame ${frameId}`);
      }
      return;
    }

    // 差分計算と侵入検知
    const diffs = computeDiff(snapshot, bgMap);
    const events = detector.evaluate(diffs);

    if (events.length > 0) {
      console.log(
        `[DETECTOR] Frame ${frameId}: Intrusion detected (${events.length} voxels)`
      );
      for (const ev of events) {
        console.log(`  voxel ${ev.key}: delta=${ev.delta.toFixed(2)}`);
      }
    } else if (frameId % 100 === 0) {
      console.log(
        `[DETECTOR] Frame ${frameId}: OK (${points.x.length} points)`
      );
    }
  } catch (err) {
    console.error("[DETECTOR] Message processing error:", err);
  }
});

ws.on("error", (err: any) => {
  console.error("[DETECTOR] WebSocket error:", err.message || err);
});

ws.on("close", () => {
  const duration = ((Date.now() - connectedTime) / 1000).toFixed(2);
  console.log(
    `[DETECTOR] Disconnected after ${duration}s (${frameId} frames processed)`
  );
  process.exit(0);
});

// クリーンアップ
process.on("SIGINT", () => {
  console.log("[DETECTOR] Shutting down...");
  ws.close();
  process.exit(0);
});

console.log("[DETECTOR] Initializing... connecting to", config.websocket_url);
