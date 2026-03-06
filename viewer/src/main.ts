/**
 * viewer/src/main.ts
 * ブラウザ向けビューワーエントリーポイント。
 * FrameDispatcher で受信フレームを 3 つの RenderLayer に分配する。
 *
 * WebSocket URL は index.html の <meta name="ws-url" content="ws://..."> か
 * URL クエリパラメータ ?ws=ws://... で上書き可能。デフォルトは localhost:8765。
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { ViewerApp } from "./index.js";
import { FrameDispatcher } from "./layers/frame-dispatcher.js";
import { PointCloudLayer } from "./layers/point-cloud-layer.js";
import { VoxelLayer } from "./layers/voxel-layer.js";
import { RangeWireframeLayer } from "./layers/range-wireframe-layer.js";
import { LayerPanel } from "./overlays/layer-panel.js";

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
const dispatcher = new FrameDispatcher();

// --- 描画レイヤー登録 ---
dispatcher.register(new PointCloudLayer(viewer));
dispatcher.register(new VoxelLayer(viewer, VOXEL_CELL_SIZE));
dispatcher.register(new RangeWireframeLayer(viewer.scene));

// --- レイヤー切替 UI ---
new LayerPanel(container, dispatcher);

// --- ステータスバー更新ヘルパー ---
const elWs = document.getElementById("status-ws");
const elFrames = document.getElementById("status-frames");
const elPoints = document.getElementById("status-points");

function setStatus(ws: string, frames?: number, points?: number) {
  if (elWs) elWs.textContent = `WS: ${ws}`;
  if (frames !== undefined && elFrames) elFrames.textContent = `フレーム: ${frames}`;
  if (points !== undefined && elPoints) elPoints.textContent = `点数: ${points}`;
}

// --- WebSocket 受信 ---
const conn = new WsConnection({
  url: WS_URL,
  reconnectInterval: 3000,
});

conn.onMessage((points) => {
  dispatcher.dispatch(points);
  setStatus("接続済み ✓", dispatcher.frameId, points.length);
});

conn.connect();
viewer.render();

console.log(`[viewer] WebSocket: ${WS_URL}`);
