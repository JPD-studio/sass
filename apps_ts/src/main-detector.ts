/**
 * main-detector.ts
 * ヘッドレス検知エントリーポイント。
 * WsConnection でフレームを受信し、背景学習 → 差分計算 → 侵入検知を行う。
 */
import { WsConnection } from "../../ws-client/src/ws-connection-node.js";
import { VoxelGrid } from "../../voxel/src/voxel-grid.js";
import { BackgroundVoxelMap } from "../../voxel/src/background-voxel-map.js";
import { computeDiff } from "../../voxel/src/voxel-diff.js";
import { IntrusionDetector } from "../../detector/src/intrusion-detector.js";
import { AdaptiveStddevThreshold } from "../../detector/src/threshold/adaptive-stddev.js";
// sensors.json (ローカル設定) が存在すればそちらを優先、なければ example にフォールバック
import { createRequire } from "module";
import { existsSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const sensorsJsonPath = join(__dirname, "../sensors.json");
const sensorsFallbackPath = join(__dirname, "../sensors.example.json");
const _require = createRequire(import.meta.url);
const config: {
  websocket_url: string;
  voxel_cell_size: number;
  detector: { strategy: string; sigma: number; min_background_samples: number };
} = existsSync(sensorsJsonPath) ? _require(sensorsJsonPath) : _require(sensorsFallbackPath);

const conn = new WsConnection({
  url: config.websocket_url,
  reconnectInterval: 3000,
});

const grid = new VoxelGrid(config.voxel_cell_size);
const bgMap = new BackgroundVoxelMap();
const strategy = new AdaptiveStddevThreshold(config.detector.sigma);
const detector = new IntrusionDetector(strategy);

const minSamples = config.detector.min_background_samples;
let frameId = 0;

conn.connect();

for await (const points of conn.frames()) {
  grid.clear();
  points.forEach((p) => grid.addPoint(p.x, p.y, p.z, frameId));
  frameId++;

  const snapshot = grid.snapshot();
  bgMap.learn(snapshot);

  if (!bgMap.isStable(minSamples)) continue;

  const diffs = computeDiff(snapshot, bgMap);
  const events = detector.evaluate(diffs);

  if (events.length > 0) {
    console.log(`[frame ${frameId}] Intrusion detected: ${events.length} voxels`);
    for (const ev of events) {
      console.log(`  key=${ev.key} delta=${ev.delta.toFixed(2)}`);
    }
  }
}
