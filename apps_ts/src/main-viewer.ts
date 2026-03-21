/**
 * main-viewer.ts
 * ブラウザ向けビューワーエントリーポイント。
 * FrameDispatcher で受信フレームを 3 つの RenderLayer に分配する。
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { resolveWsUrl } from "../../ws-client/src/resolve-ws-url.js";
import { ViewerApp } from "../../viewer/src/index.js";
import { FrameDispatcher } from "../../viewer/src/layers/frame-dispatcher.js";
import { PointCloudLayer } from "../../viewer/src/layers/point-cloud-layer.js";
import { VoxelLayer } from "../../viewer/src/layers/voxel-layer.js";
import { RangeWireframeLayer } from "../../viewer/src/layers/range-wireframe-layer.js";
import { LayerPanel } from "../../viewer/src/overlays/layer-panel.js";
import config from "../sensors.example.json" with { type: "json" };

const container = document.getElementById("viewer-container") as HTMLElement;
const viewer = new ViewerApp(container);
const dispatcher = new FrameDispatcher();

// --- 描画レイヤー登録 ---
// 注意: 現行は updatePoints() を呼んでいなかった（ボクセルのみ）。
// PointCloudLayer 追加は挙動変更（点群表示が新規追加される）。
dispatcher.register(new PointCloudLayer(viewer));
dispatcher.register(new VoxelLayer(viewer, config.voxel_cell_size));
dispatcher.register(new RangeWireframeLayer(viewer.scene));

// --- レイヤー切替 UI ---
new LayerPanel(container, dispatcher);

// --- WebSocket 受信 ---
(async () => {
  const wsUrl = await resolveWsUrl();
  const conn = new WsConnection({
    url: wsUrl,
    reconnectInterval: 3000,
  });

  conn.onMessage((points) => {
    dispatcher.dispatch(points);
  });

  conn.connect();
  viewer.render();
})();
