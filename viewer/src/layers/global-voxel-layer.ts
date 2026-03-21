/**
 * global-voxel-layer.ts
 *
 * グローバルモード用ボクセルレイヤー（WGS84直接グリッド化）。
 *
 * 処理フロー:
 *   センサーローカル → WGS84 → WGS84グリッド直接化
 *   キー形式: "ilat:ilng:ialt" (WGS84 各軸の floor インデックス)
 *
 * Encode.GridLine で ALoGS グリッド最小単位を定義し、
 * WGS84空間上でDirectlyグリッド化する（ENU経由なし）。
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
  private readonly _unitM: number;
  private readonly _latUnit: number;  // 南北方向の度数差（vendor/alogs GridLine()から取得）
  private readonly _lngUnit: number;  // 東西方向の度数差（vendor/alogs GridLine()から取得、コサイン誤差含む）
  private readonly _mountLat: number; // グリッド中心の緯度（コサイン補正用）

  constructor(
    viewer: ViewerApp,
    mount: SensorMount,
    unitM: number = 1.0,
    gridMode: "wgs84" | "enu" = "wgs84",
  ) {
    this._unitM = unitM;
    this._mountLat = mount.position.lat;  // グリッド中心の緯度を保存
    this._sensorTransformer = new CoordinateTransformer(mount);

    // Encode.GridLine() から度数差を取得（コサイン誤差を織り込み済み）
    const { latUnit, lngUnit } = this._getGridUnits(unitM);
    this._latUnit = latUnit;
    this._lngUnit = lngUnit;

    console.log(
      `[GlobalVoxelLayer] GridLine() 度数差: ` +
      `latUnit=${latUnit.toExponential(4)}, lngUnit=${lngUnit.toExponential(4)}, ` +
      `ratio(lng/lat)=${(lngUnit / latUnit).toFixed(4)}`
    );

    // 度数差から直接メートル距離を計算（理論値）
    const distTheory = GlobalVoxelRenderer.getDistanceFromDegreesDifference(
      AKASHI_LAT,
      latUnit,
      lngUnit
    );
    console.log(
      `[GlobalVoxelLayer] 理論値（度数→メートル直計）: ` +
      `north=${distTheory.north.toFixed(3)}m, east=${distTheory.east.toFixed(3)}m, ` +
      `ratio=${(distTheory.east / distTheory.north).toFixed(4)}`
    );

    this._renderer = new GlobalVoxelRenderer(
      viewer.scene, unitM, this._sensorTransformer, latUnit, lngUnit
    );
  }

  onFrame(points: PointData[], frameId: number): void {
    this._renderer.update(this._buildSnapshot(points, frameId));
  }

  setVisible(visible: boolean): void {
    this._renderer.mesh.visible = visible;
  }

  /** 最後に描画されたボクセルの3辺寸法を取得 */
  getLastVoxelDimensions(): { east: number; north: number; up: number } | undefined {
    return this._renderer.getLastVoxelDimensions();
  }

  dispose(): void {
    this._renderer.dispose();
  }

  /**
   * Encode.GridLine() で ALoGS グリッド定義を取得
   * 南北・東西の度数差を分けて返す
   *
   * ⚠️ GridLine() の unitList = [1, 2, 4, 5, 10, ...] のため、
   *    0.5 などはリスト外の値を渡しても unit=1 へ snap される。
   *    そのため、常に unit=1 (最小有効値) で呼び出して1m相当の
   *    base 度数差を取得し、unitM 倍して細分化する。
   */
  private _getGridUnits(unitM: number): { latUnit: number; lngUnit: number } {
    // 常に unit=1 で呼び出す（unitList 最小値 = 1m）
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = (Encode as any).GridLine(AKASHI_LAT, AKASHI_LNG, 1, 4);
    const { grid } = JSON.parse(raw) as { grid: { lats: number[]; lngs: number[] } };

    // 1m 相当の度数差を取得
    const latUnit1 = grid.lats.length >= 2 ? grid.lats[1] - grid.lats[0] : 0.000009;
    const lngUnit1 = grid.lngs.length >= 2 ? grid.lngs[1] - grid.lngs[0] : 0.000011;

    // unitM 倍して実際のセルサイズに対応する度数差を計算
    const latUnit = latUnit1 * unitM;
    const lngUnit = lngUnit1 * unitM;

    console.log(
      `[GlobalVoxelLayer] GridLine(unit=1)から取得: latUnit1=${latUnit1.toExponential(4)}, lngUnit1=${lngUnit1.toExponential(4)}` +
      ` → unitM=${unitM} 倍: latUnit=${latUnit.toExponential(4)}, lngUnit=${lngUnit.toExponential(4)}`
    );

    return { latUnit, lngUnit };
  }

  /** 点群 → WGS84グリッドキー "ilat:ilng:ialt" の VoxelSnapshot */
  private _buildSnapshot(points: PointData[], frameId: number): VoxelSnapshot {
    const cells = new Map<VoxelKey, VoxelState>();

    for (const p of points) {
      // センサーローカル → WGS84 (Ouster は Z-up 座標系 — 反転不要)
      const wgs84 = this._sensorTransformer.transformPoint(p.x, p.y, p.z);

      // WGS84グリッド単位でスナップ（GridLine()の度数差を使用）
      const ilat = Math.floor(wgs84.lat / this._latUnit);
      const ilng = Math.floor(wgs84.lng / this._lngUnit);
      const ialt = Math.floor(wgs84.alt / this._unitM);
      const key: VoxelKey = `${ilat}:${ilng}:${ialt}`;

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
