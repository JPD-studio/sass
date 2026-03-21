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

const container = document.getElementById("viewer-container") as HTMLElement;
const viewer = new ViewerApp(container);
const dispatcher = new FrameDispatcher();

// --- 描画レイヤー登録 ---
// 注意: 現行は updatePoints() を呼んでいなかった（ボクセルのみ）。
// PointCloudLayer 追加は挙動変更（点群表示が新規追加される）。
dispatcher.register(new PointCloudLayer(viewer));

// --- レイヤー切替 UI ---
new LayerPanel(container, dispatcher);

// --- WebSocket 受信 ---
(async () => {
  // viewer/config.json から voxel_cell_size を取得（存在しなければデフォルト 1.0）
  let voxelCellSize = 1.0;
  try {
    const resp = await fetch("/config.json");
    if (resp.ok) {
      const cfg = (await resp.json()) as { voxel_cell_size?: number };
      voxelCellSize = cfg.voxel_cell_size ?? 1.0;
    }
  } catch {
    /* ネットワーク不達・ファイル不在時はデフォルト値 1.0 で続行 */
  }

  dispatcher.register(new VoxelLayer(viewer, voxelCellSize));
  dispatcher.register(new RangeWireframeLayer(viewer.scene));

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
