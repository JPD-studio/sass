/**
 * viewer/src/main.ts
 * ブラウザ向けビューワーエントリーポイント。
 * WsConnection でフレームを受信し、VoxelGrid でボクセル化して ViewerApp に渡す。
 *
 * WebSocket URL は index.html の <meta name="ws-url" content="ws://..."> か
 * URL クエリパラメータ ?ws=ws://... で上書き可能。デフォルトは localhost:8765。
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { VoxelGrid } from "../../voxel/src/voxel-grid.js";
import { ViewerApp } from "./index.js";

// WebSocket URL の解決（URLパラメータ > metaタグ > 同一ホスト自動解決）
function resolveWsUrl(): string {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("ws");
  if (fromQuery) return fromQuery;

  const meta = document.querySelector<HTMLMetaElement>('meta[name="ws-url"]');
  if (meta?.content) return meta.content;

  // ouster_bridge3 同様: 同一ホストの 8765 ポートに接続
  return `ws://${window.location.hostname}:8765`;
}

const WS_URL = resolveWsUrl();
const VOXEL_CELL_SIZE = 1.0;

const container = document.getElementById("viewer-container") as HTMLElement;
if (!container) throw new Error("#viewer-container が見つかりません");

const viewer = new ViewerApp(container);

// ステータスバー更新ヘルパー
const elWs = document.getElementById("status-ws");
const elFrames = document.getElementById("status-frames");
const elPoints = document.getElementById("status-points");

function setStatus(ws: string, frames?: number, points?: number) {
  if (elWs) elWs.textContent = `WS: ${ws}`;
  if (frames !== undefined && elFrames) elFrames.textContent = `フレーム: ${frames}`;
  if (points !== undefined && elPoints) elPoints.textContent = `点数: ${points}`;
}

const conn = new WsConnection({
  url: WS_URL,
  reconnectInterval: 3000,
});

const grid = new VoxelGrid(VOXEL_CELL_SIZE);
let frameId = 0;

conn.onMessage((points) => {
  // 生の点群表示（ouster_bridge3 同等のカラー点群）
  viewer.updatePoints(points);

  // ボクセル化して半透明ボクセル表示
  grid.clear();
  points.forEach((p) => grid.addPoint(p.x, p.y, p.z, frameId));
  frameId++;
  viewer.updateVoxels(grid.snapshot(), VOXEL_CELL_SIZE);
  setStatus("接続済み ✓", frameId, points.length);
});

conn.connect();
viewer.render();

console.log(`[viewer] WebSocket: ${WS_URL}`);
