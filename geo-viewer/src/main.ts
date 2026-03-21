/**
 * geo-viewer/src/main.ts
 *
 * CesiumJS を使用した地球儀ビューワー（表示専用）
 * WebSocket から受信したセンサーローカル XYZ 点群を
 * CoordinateTransformer で WGS84 に変換してリアルタイム表示する。
 *
 * ⚠️ 検知ロジックは含まない — main-detector.ts に集約
 * ⚠️ spatial-id-converter.ts は Node.js 専用のため import 禁止
 * ✅ coordinate-transform.ts はブラウザ互換 (Node.js API 不使用)
 */

import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

import { CoordinateTransformer } from "../../spatial-grid/src/coordinate-transform.js";
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { resolveWsUrl } from "../../ws-client/src/resolve-ws-url.js";
import { PointCloudLayer } from "./point-cloud-layer.js";
import type { GeoViewerConfig } from "./types.js";

// CesiumJS の静的アセットパス (webpack の CopyPlugin でコピーされる)
(window as Window & { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = "/dist/";

// 環境変数 (dotenv-webpack で注入、未設定時は空文字)
const CESIUM_ION_TOKEN: string = (process.env as Record<string, string>).CESIUM_ION_TOKEN ?? "";
Cesium.Ion.defaultAccessToken = CESIUM_ION_TOKEN;

// ── 設定読み込み（start.sh が config.json を生成） ──
const configResp = await fetch("/config.json");
if (!configResp.ok) {
  throw new Error(`config.json の読み込みに失敗: ${configResp.status}`);
}
const config = await configResp.json() as GeoViewerConfig;
const mount = config.mount;

// ── CesiumJS Viewer 初期化 ──
const viewer = new Cesium.Viewer("cesiumContainer", {
  baseLayerPicker: false,
  timeline: false,
  animation: false,
});

// Google Photorealistic 3D Tiles を追加 (CesiumJS 1.104+)
// Jetson の GPU メモリ不足時はスキップしてテレインのみで続行
try {
  const tileset = await Cesium.createGooglePhotorealistic3DTileset();
  viewer.scene.primitives.add(tileset);
} catch (e) {
  console.warn("[Geo-Viewer] Google 3D Tiles 読み込み失敗 — terrain のみで続行:", e);
}

// 初期カメラ位置をセンサーマウント位置の上空に設定
viewer.camera.setView({
  destination: Cesium.Cartesian3.fromDegrees(
    mount.position.lng,
    mount.position.lat,
    500  // 500m 上空
  ),
  orientation: {
    heading: Cesium.Math.toRadians(0),
    pitch: Cesium.Math.toRadians(-45),
    roll: 0,
  },
});

// ── 座標変換 (ブラウザ互換) ──
const transformer = new CoordinateTransformer(mount);

// ── 点群レイヤー ──
const pointLayer = new PointCloudLayer(viewer.scene);

// ── FPS / 点数表示 ──
const fpsEl = document.getElementById("fps");
const pointCountEl = document.getElementById("point-count");
let lastTime = performance.now();
let frameCount = 0;

// ── WebSocket 接続 ──
const WS_URL = await resolveWsUrl();
const conn = new WsConnection({
  url: WS_URL,
  reconnectInterval: 3000,
});

console.log(`[Geo-Viewer] WebSocket 接続: ${WS_URL}`);
conn.connect();

for await (const localPoints of conn.frames()) {
  // センサーローカル XYZ → WGS84 変換
  const wgsPoints = transformer.transformPointCloud(localPoints);
  pointLayer.update(wgsPoints);

  // FPS 計算 (10フレームごと)
  frameCount++;
  if (frameCount % 10 === 0) {
    const now = performance.now();
    const fps = (10 / ((now - lastTime) / 1000)).toFixed(1);
    lastTime = now;
    if (fpsEl) fpsEl.textContent = `FPS: ${fps}`;
    if (pointCountEl) pointCountEl.textContent = `Points: ${pointLayer.pointCount}`;
  }
}
