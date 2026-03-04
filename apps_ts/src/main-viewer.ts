/**
 * main-viewer.ts
 * ブラウザ向けビューワーエントリーポイント。
 * WsConnection でフレームを受信し、VoxelGrid でボクセル化して ViewerApp に渡す。
 */
import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { VoxelGrid } from "../../voxel/src/voxel-grid.js";
import { ViewerApp } from "../../viewer/src/index.js";
import config from "../sensors.example.json" with { type: "json" };

const container = document.getElementById("viewer-container") as HTMLElement;
const viewer = new ViewerApp(container);

const conn = new WsConnection({
  url: config.websocket_url,
  reconnectInterval: 3000,
});

const grid = new VoxelGrid(config.voxel_cell_size);
let frameId = 0;

conn.onMessage((points) => {
  grid.clear();
  points.forEach((p) => grid.addPoint(p.x, p.y, p.z, frameId));
  frameId++;
  viewer.updateVoxels(grid.snapshot());
});

conn.connect();
viewer.render();
