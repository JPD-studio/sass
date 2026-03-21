/**
 * viewer/src/main.ts
 * ブラウザ向けビューワーエントリーポイント。
 *
 * config.json を fetch してモードを決定:
 *   voxel_mode: "local"  → VoxelLayer (センサーローカル座標系) [デフォルト]
 *   voxel_mode: "global" → GlobalVoxelLayer (ALoGS 空間ID + WGS84 逆変換)
 *   voxel_mode: "both"   → 左右分割表示 (左: local / 右: global)
 *
 * WebSocket URL は ws-client の resolveWsUrl() で一元解決:
 *   URL クエリ ?ws= → <meta name="ws-url"> → /websocket.json → hostname:8765
 *
 * ※ top-level await は Jetson Chromium との互換性問題があるため
 *    async IIFE パターンを使用 (webpack experiments.topLevelAwait 不要)
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { resolveWsUrl } from "../../ws-client/src/resolve-ws-url.js";
import { ViewerApp } from "./index.js";
import { FrameDispatcher } from "./layers/frame-dispatcher.js";
import { PointCloudLayer } from "./layers/point-cloud-layer.js";
import { VoxelLayer } from "./layers/voxel-layer.js";
import { GlobalVoxelLayer } from "./layers/global-voxel-layer.js";
import { RangeWireframeLayer } from "./layers/range-wireframe-layer.js";
import { LayerPanel } from "./overlays/layer-panel.js";
import type { SensorMount } from "../../spatial-grid/src/types.js";

// ── 設定型 ──
interface ViewerConfig {
  voxel_mode?: "local" | "global" | "both";
  voxel_cell_size?: number;
  global_voxel_unit_m?: number;
  global_grid_mode?: "wgs84" | "enu";
  coin?: {
    position: [number, number, number];
    radius_m?: number;
    height_m?: number;
    rotation?: { x?: number; y?: number; z?: number };
  };
  mount?: {
    position: { lat: number; lng: number; alt: number };
    orientation: { heading: number; pitch: number; roll: number };
    mounting_type?: string;
  };
}

// ── ステータスバー要素 (DOMContentLoaded 後に参照) ──
function setStatus(ws: string, frames?: number, points?: number) {
  const elWs     = document.getElementById("status-ws");
  const elFrames = document.getElementById("status-frames");
  const elPoints = document.getElementById("status-points");
  if (elWs)     elWs.textContent     = `WS: ${ws}`;
  if (frames !== undefined && elFrames) elFrames.textContent = `フレーム: ${frames}`;
  if (points !== undefined && elPoints) elPoints.textContent = `点数: ${points}`;
}

// ── マウント情報を SensorMount 型に変換 ──
function buildMount(cfg: ViewerConfig): SensorMount | null {
  if (!cfg.mount) return null;
  return {
    position: cfg.mount.position,
    orientation: cfg.mount.orientation,
    mounting_type: cfg.mount.mounting_type ?? "pole_mounted",
  };
}

// ================================================================
//  メイン初期化 — async IIFE
//  top-level await を使わないことで webpack の実験的機能に依存しない
// ================================================================
(async () => {
  // ── config.json 読み込み (失敗時はデフォルト値) ──
  let config: ViewerConfig = {};
  try {
    const resp = await fetch("/config.json");
    if (resp.ok) config = await resp.json() as ViewerConfig;
  } catch {
    // config.json がない場合はデフォルト動作 (ローカルモード)
  }

  const WS_URL    = await resolveWsUrl();
  const voxelMode = config.voxel_mode ?? "local";
  const cellSize  = config.voxel_cell_size ?? 1.0;
  const unitM     = config.global_voxel_unit_m ?? 10.0;
  const gridMode  = config.global_grid_mode ?? "wgs84";

  // ── デバッグ出力 ──
  console.log("[VIEWER] WebSocket URL:", WS_URL);
  console.log("[VIEWER] window.location.hostname:", window.location.hostname);
  console.log("[VIEWER] voxel_mode:", voxelMode);

  // ── WebSocket 接続 (共通) ──
  const conn = new WsConnection({ url: WS_URL, reconnectInterval: 3000 });

  // ================================================================
  //  スプリットモード (voxel_mode: "both")
  //  左ペイン: ローカルボクセル / 右ペイン: グローバルボクセル
  // ================================================================
  if (voxelMode === "both") {
    document.body.classList.add("split-mode");

    const containerLeft  = document.getElementById("viewer-left")  as HTMLElement;
    const containerRight = document.getElementById("viewer-right") as HTMLElement;

    // カメラ同期用フラグ（無限ループ防止）
    let syncing = false;

    // 左右のViewerApp を作成（カメラ同期コールバック付き）
    const viewerLeft  = new ViewerApp(containerLeft, config.coin, (state) => {
      if (syncing) return;
      syncing = true;
      viewerRight.setCameraState(state);
      syncing = false;
    });

    const viewerRight = new ViewerApp(containerRight, config.coin, (state) => {
      if (syncing) return;
      syncing = true;
      viewerLeft.setCameraState(state);
      syncing = false;
    });

    const dispLeft  = new FrameDispatcher();
    const dispRight = new FrameDispatcher();

    // 左: ローカルボクセル
    dispLeft.register(new PointCloudLayer(viewerLeft));
    dispLeft.register(new VoxelLayer(viewerLeft, cellSize));
    const wireframeLeft = new RangeWireframeLayer(viewerLeft.scene);
    dispLeft.register(wireframeLeft);
    new LayerPanel(containerLeft, dispLeft);

    // 右: グローバルボクセル
    dispRight.register(new PointCloudLayer(viewerRight));
    const mount = buildMount(config);
    let globalVoxelLayer: GlobalVoxelLayer | null = null;
    if (mount) {
      globalVoxelLayer = new GlobalVoxelLayer(viewerRight, mount, unitM, gridMode);
      dispRight.register(globalVoxelLayer);
    } else {
      dispRight.register(new VoxelLayer(viewerRight, cellSize));
      console.warn("[viewer] both モードで mount 未設定: 右ペインをローカルモードで代替");
    }
    const wireframeRight = new RangeWireframeLayer(viewerRight.scene);
    dispRight.register(wireframeRight);
    new LayerPanel(containerRight, dispRight);

    // filter_config メッセージでワイヤーフレーム更新
    conn.onRawMessage((msg) => {
      if (msg.type === "filter_config") {
        if (msg.frustum)    { wireframeLeft.updateConfig(msg.frustum);            wireframeRight.updateConfig(msg.frustum); }
        if (msg.cylindrical){ wireframeLeft.updateCylindricalConfig(msg.cylindrical); wireframeRight.updateCylindricalConfig(msg.cylindrical); }
        if (msg.spherical)  { wireframeLeft.updateSphericalConfig(msg.spherical); wireframeRight.updateSphericalConfig(msg.spherical); }
        if (msg.box)        { wireframeLeft.updateBoxConfig(msg.box);             wireframeRight.updateBoxConfig(msg.box); }
        if (msg.polygon)    { wireframeLeft.updatePolygonConfig(msg.polygon);     wireframeRight.updatePolygonConfig(msg.polygon); }
      }
    });

    conn.onMessage((points) => {
      dispLeft.dispatch(points);
      dispRight.dispatch(points);
      setStatus("接続済み ✓", dispLeft.frameId, points.length);

      // グローバルボクセルの寸法をデバッグ表示
      if (globalVoxelLayer) {
        const dim = globalVoxelLayer.getLastVoxelDimensions();
        if (dim) {
          const el = document.getElementById("voxel-dimensions");
          if (el) {
            el.textContent = `Global Voxel: EW=${dim.east.toFixed(4)}m NS=${dim.north.toFixed(4)}m UD=${dim.up.toFixed(4)}m U=${dim.up}`;
            el.style.display = "block";
          }
        }
      }
    });

    viewerLeft.render();
    viewerRight.render();
    console.log(`[viewer] 分割モード: 左=local(${cellSize}m), 右=global(${unitM}m)`);

  // ================================================================
  //  シングルモード (voxel_mode: "local" | "global")
  // ================================================================
  } else {
    const container = document.getElementById("viewer-container") as HTMLElement;
    if (!container) throw new Error("#viewer-container が見つかりません");

    const viewer     = new ViewerApp(container, config.coin);
    const dispatcher = new FrameDispatcher();
    let globalVoxelLayer: GlobalVoxelLayer | null = null;

    dispatcher.register(new PointCloudLayer(viewer));

    if (voxelMode === "global") {
      const mount = buildMount(config);
      if (mount) {
        globalVoxelLayer = new GlobalVoxelLayer(viewer, mount, unitM, gridMode);
        dispatcher.register(globalVoxelLayer);
        console.log(`[viewer] グローバルモード: unit=${unitM}m, grid=${gridMode}, mount=(${mount.position.lat}, ${mount.position.lng})`);
      } else {
        dispatcher.register(new VoxelLayer(viewer, cellSize));
        console.warn("[viewer] global モードで mount 未設定: ローカルモードで代替");
      }
    } else {
      dispatcher.register(new VoxelLayer(viewer, cellSize));
      console.log(`[viewer] ローカルモード: cellSize=${cellSize}m`);
    }

    const wireframeSingle = new RangeWireframeLayer(viewer.scene);
    dispatcher.register(wireframeSingle);
    new LayerPanel(container, dispatcher);

    // filter_config メッセージでワイヤーフレーム更新
    conn.onRawMessage((msg) => {
      if (msg.type === "filter_config") {
        if (msg.frustum)    wireframeSingle.updateConfig(msg.frustum);
        if (msg.cylindrical) wireframeSingle.updateCylindricalConfig(msg.cylindrical);
        if (msg.spherical)  wireframeSingle.updateSphericalConfig(msg.spherical);
        if (msg.box)        wireframeSingle.updateBoxConfig(msg.box);
        if (msg.polygon)    wireframeSingle.updatePolygonConfig(msg.polygon);
      }
    });

    conn.onMessage((points) => {
      dispatcher.dispatch(points);
      setStatus("接続済み ✓", dispatcher.frameId, points.length);

      // グローバルボクセルの寸法をデバッグ表示
      if (globalVoxelLayer) {
        const dim = globalVoxelLayer.getLastVoxelDimensions();
        if (dim) {
          const el = document.getElementById("voxel-dimensions");
          if (el) {
            el.textContent = `Global Voxel: EW=${dim.east.toFixed(4)}m NS=${dim.north.toFixed(4)}m UD=${dim.up.toFixed(4)}m U=${dim.up}`;
            el.style.display = "block";
          }
        }
      }
    });

    viewer.render();
  }

  conn.connect();
  console.log(`[viewer] WebSocket: ${WS_URL}, mode: ${voxelMode}`);
})();
