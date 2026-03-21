/**
 * main-detector.js - Node.js環境用の侵入検知ヘッドレスアプリ
 * WebSocketでPCAPサーバーからデータを受信し、リアルタイム侵入検知を実行
 */
import WebSocket from "ws";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { VoxelGrid } from "../voxel/src/voxel-grid.js";
import { BackgroundVoxelMap } from "../voxel/src/background-voxel-map.js";
import { computeDiff } from "../voxel/src/voxel-diff.js";
import { IntrusionDetector } from "../detector/src/intrusion-detector.js";
import { AdaptiveStddevThreshold } from "../detector/src/threshold/adaptive-stddev.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sensorsPath = path.join(__dirname, "../sensors.json");
const sensorsFallbackPath = path.join(__dirname, "../sensors.example.json");

// 設定を読み込む
let config;
try {
  const content = fs.readFileSync(
    fs.existsSync(sensorsPath) ? sensorsPath : sensorsFallbackPath,
    "utf-8"
  );
  config = JSON.parse(content);
  console.log("[DETECTOR] Config loaded");
  console.log(`  WebSocket URL: ${config.websocket_url}`);
  console.log(`  Voxel size: ${config.voxel_cell_size}m`);
  console.log(`  Min samples for stability: ${config.detector.min_background_samples}`);
} catch (err) {
  console.error("[DETECTOR] Error loading config:", err.message);
  process.exit(1);
}

// グローバルオブジェクト初期化
const grid = new VoxelGrid(config.voxel_cell_size);
const bgMap = new BackgroundVoxelMap();
const strategy = new AdaptiveStddevThreshold(config.detector.sigma);
const detector = new IntrusionDetector(strategy);
const minSamples = config.detector.min_background_samples;

let frameId = 0;
let startTime = Date.now();
let connectedTime = null;
let framesReceived = 0;
let intrusionsDetected = 0;

// WebSocket接続
const ws = new WebSocket(config.websocket_url);

ws.on("open", () => {
  connectedTime = Date.now();
  console.log(`[DETECTOR] Connected to ${config.websocket_url}`);
});

ws.on("message", (data) => {
  try {
    const message = typeof data === "string" ? data : data.toString();
    const frame = JSON.parse(message);

    if (!frame.points || !frame.points.x) {
      return;
    }

    framesReceived++;
    const points = frame.points;

    // ボクセルグリッドにポイントを追加
    grid.clear();
    for (let i = 0; i < points.x.length; i++) {
      grid.addPoint(points.x[i], points.y[i], points.z[i], frameId);
    }
    frameId++;

    // 背景シーン学習
    const snapshot = grid.snapshot();
    bgMap.learn(snapshot);

    // 安定性チェック
    if (!bgMap.isStable(minSamples)) {
      if (frameId % 100 === 0) {
        const elapsed = (Date.now() - startTime) / 1000;
        console.log(
          `[DETECTOR] Learning background... frame ${frameId} (${elapsed.toFixed(1)}s)`
        );
      }
      return;
    }

    // 差分計算と侵入検知
    const diffs = computeDiff(snapshot, bgMap);
    const events = detector.evaluate(diffs);

    if (events.length > 0) {
      intrusionsDetected++;
      console.log(
        `[DETECTOR] 🚨 INTRUSION DETECTED at frame ${frameId}: ${events.length} anomalous voxels`
      );
      // 初回検知のみ詳細を出力
      if (intrusionsDetected <= 3) {
        for (let i = 0; i < Math.min(5, events.length); i++) {
          const ev = events[i];
          console.log(`    Voxel ${i + 1}: key=${ev.key}, delta=${ev.delta.toFixed(3)}`);
        }
      }
    } else if (frameId % 200 === 0) {
      const elapsed = (Date.now() - startTime) / 1000;
      console.log(
        `[DETECTOR] ✓ Frame ${frameId}: OK (${points.x.length} points) - Elapsed: ${elapsed.toFixed(1)}s`
      );
    }
  } catch (err) {
    console.error("[DETECTOR] Error processing message:", err.message);
  }
});

ws.on("error", (err) => {
  console.error("[DETECTOR] WebSocket error:", err.message);
});

ws.on("close", () => {
  const duration = connectedTime ? (Date.now() - connectedTime) / 1000 : 0;
  console.log("\n[DETECTOR] Connection closed");
  console.log(`  Session duration: ${duration.toFixed(1)}s`);
  console.log(`  Frames received: ${framesReceived}`);
  console.log(`  Frames processed: ${frameId}`);
  console.log(`  Intrusions detected: ${intrusionsDetected}`);
  process.exit(0);
});

// クリーンアップハンドラー
process.on("SIGINT", () => {
  console.log("\n[DETECTOR] Shutting down...");
  ws.close();
});

console.log("[DETECTOR] Initializing detector...");
console.log(`  Connecting to ${config.websocket_url}...`);
