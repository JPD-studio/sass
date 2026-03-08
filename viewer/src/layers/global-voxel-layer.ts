/**
 * global-voxel-layer.ts
 *
 * グローバルモード用ボクセルレイヤー。
 *
 * グリッド方式 (config.json の global_grid_mode で切り替え):
 *
 *   "wgs84" (デフォルト):
 *     Encode.GridLine で明石市立天文科学館（JST 基準子午線 135°E）付近の
 *     ALoGS グリッド SW 角を取得 → 地球上に固定されたグリッド原点。
 *     向きの異なる複数センサーが同じ場所を計測すれば同じキーになる。
 *
 *   "enu":
 *     センサーマウント位置を原点とした ENU 座標系でグリッドを切る。
 *     センサー固有の原点なため異なるセンサー間でキーは一致しないが、
 *     ローカルボクセルとの並置比較に便利。
 *
 * キー形式: "ie:in:iu" (ENU 各軸の floor インデックス) — 両モード共通
 *
 * ⚠️ ブラウザ (webpack) 専用 — vendor/alogs は javascript/auto で CJS バンドル済み
 */

import Encode from "../../../vendor/alogs/Encode.js";
import { CoordinateTransformer } from "../../../spatial-grid/src/coordinate-transform.js";
import type { SensorMount } from "../../../spatial-grid/src/types.js";
import type { PointData } from "../../../ws-client/src/types.js";
import type { VoxelKey, VoxelSnapshot, VoxelState } from "../../../voxel/src/types.js";
import { GlobalVoxelRenderer } from "../renderers/global-voxel-renderer.js";
import type { RenderLayer } from "./types.js";
import type { ViewerApp } from "../index.js";

// 明石市立天文科学館（JST 基準子午線 135°E）— グローバルグリッド基準クエリ点
const AKASHI_LAT = 34.6453;
const AKASHI_LNG = 135.0;

export class GlobalVoxelLayer implements RenderLayer {
  readonly name = "global-voxel";
  readonly label = "グローバルボクセル";
  enabled = true;

  private readonly _renderer: GlobalVoxelRenderer;
  private readonly _sensorTransformer: CoordinateTransformer;
  private readonly _gridTransformer: CoordinateTransformer;
  private readonly _unitM: number;

  constructor(
    viewer: ViewerApp,
    mount: SensorMount,
    unitM: number = 1.0,
    gridMode: "wgs84" | "enu" = "wgs84",
  ) {
    this._unitM = unitM;
    this._sensorTransformer = new CoordinateTransformer(mount);

    // heading=90 → R_sensor = 単位行列 → inverseTransformPoint が純粋な ENU を返す
    let gridOriginPosition: { lat: number; lng: number; alt: number };
    if (gridMode === "enu") {
      // ENU モード: センサーマウント位置を原点
      gridOriginPosition = mount.position;
      console.log(`[GlobalVoxelLayer] ENU モード: センサー位置を原点に使用`);
    } else {
      // WGS84 モード: 明石付近の ALoGS グリッド SW 角を原点
      const origin = this._findGridOrigin(AKASHI_LAT, AKASHI_LNG, unitM);
      gridOriginPosition = { lat: origin.lat, lng: origin.lng, alt: 0 };
      console.log(`[GlobalVoxelLayer] WGS84 モード: グリッド原点 lat=${origin.lat}, lng=${origin.lng}`);
    }

    const gridMount: SensorMount = {
      position: gridOriginPosition,
      orientation: { heading: 90, pitch: 0, roll: 0 },
      mounting_type: "pole_mounted",
    };
    this._gridTransformer = new CoordinateTransformer(gridMount);
    this._renderer = new GlobalVoxelRenderer(
      viewer.scene, unitM, this._gridTransformer, this._sensorTransformer
    );
  }

  onFrame(points: PointData[], frameId: number): void {
    this._renderer.update(this._buildSnapshot(points, frameId));
  }

  setVisible(visible: boolean): void {
    this._renderer.mesh.visible = visible;
  }

  dispose(): void {
    this._renderer.dispose();
  }

  /**
   * Encode.GridLine で ALoGS グリッド SW 角 (lat, lng) を求める。
   * この点を origin とした CoordinateTransformer (heading=90) は
   * inverseTransformPoint で純粋な ENU [m] を返す。
   */
  private _findGridOrigin(lat: number, lng: number, unit: number): { lat: number; lng: number } {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = (Encode as any).GridLine(lat, lng, unit, 4);
    const { grid } = JSON.parse(raw) as { grid: { lats: number[]; lngs: number[] } };
    const southLines = grid.lats.filter((v: number) => v <= lat);
    const westLines  = grid.lngs.filter((v: number) => v <= lng);
    return {
      lat: southLines.length > 0 ? Math.max(...southLines) : lat,
      lng: westLines.length  > 0 ? Math.max(...westLines)  : lng,
    };
  }

  /** 点群 → ENU グリッドキー "ie:in:iu" の VoxelSnapshot */
  private _buildSnapshot(points: PointData[], frameId: number): VoxelSnapshot {
    const cells = new Map<VoxelKey, VoxelState>();

    for (const p of points) {
      // センサーローカル → WGS84 (Z は下向きなので反転)
      const wgs84 = this._sensorTransformer.transformPoint(p.x, p.y, -p.z);

      // WGS84 → ENU from グリッド原点 (heading=90 → R_sensor=I → x=E, y=N, z=U)
      const enu = this._gridTransformer.inverseTransformPoint(wgs84.lat, wgs84.lng, wgs84.alt);

      // unitM グリッドにスナップ
      const ie  = Math.floor(enu.x / this._unitM);
      const in_ = Math.floor(enu.y / this._unitM);
      const iu  = Math.floor(enu.z / this._unitM);
      const key: VoxelKey = `${ie}:${in_}:${iu}`;

      const existing = cells.get(key);
      if (existing) {
        existing.count += 1;
        existing.lastUpdated = frameId;
      } else {
        cells.set(key, { count: 1, lastUpdated: frameId });
      }
    }

    return cells;
  }
}
