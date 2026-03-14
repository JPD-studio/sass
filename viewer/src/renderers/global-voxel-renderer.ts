/**
 * global-voxel-renderer.ts
 *
 * WGS84グリッドキー ("ilat:ilng:ialt") をもつ VoxelSnapshot を 
 * Three.js InstancedMesh で描画する。
 *
 * 重要：各ボクセルのサイズを正確に計算（コサイン誤差対応）
 *
 * 処理フロー:
 *   1. キー "ilat:ilng:ialt" → WGS84セル中心座標を計算
 *   2. 隣接セル（東西・南北）も同様に計算
 *   3. 各座標を sensorTransformer.inverseTransformPoint() で変換
 *   4. センサーローカル XYZ での実距離を計算
 *   5. その距離を各軸のスケーリング係数として適用
 */

import * as THREE from "three";
import type { CoordinateTransformer } from "../../../spatial-grid/src/coordinate-transform.js";
import type { VoxelSnapshot } from "../../../voxel/src/types.js";

const MAX_INSTANCES = 50_000;

export class GlobalVoxelRenderer {
  private readonly _mesh: THREE.InstancedMesh;
  private readonly _dummy = new THREE.Object3D();
  private readonly _unitM: number;
  private readonly _latUnit: number;  // vendor/alogs GridLine() から取得した南北度数差
  private readonly _lngUnit: number;  // vendor/alogs GridLine() から取得した東西度数差（コサイン誤差含む）
  private readonly _sensorTransformer: CoordinateTransformer;

  /** 最後に描画されたボクセルの3辺サイズ（デバッグ用） */
  private _lastVoxelDimensions?: { east: number; north: number; up: number };

  constructor(
    scene: THREE.Scene,
    unitM: number,
    sensorTransformer: CoordinateTransformer,
    latUnit: number,  // GridLine()から得た南北度数差
    lngUnit: number,  // GridLine()から得た東西度数差
  ) {
    this._unitM = unitM;
    this._latUnit = latUnit;
    this._lngUnit = lngUnit;
    this._sensorTransformer = sensorTransformer;

    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshStandardMaterial({
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
    });
    this._mesh = new THREE.InstancedMesh(geometry, material, MAX_INSTANCES);
    this._mesh.instanceColor = new THREE.InstancedBufferAttribute(
      new Float32Array(MAX_INSTANCES * 3), 3
    );
    this._mesh.count = 0;
    scene.add(this._mesh);
  }

  get mesh(): THREE.InstancedMesh {
    return this._mesh;
  }

  /** 最後に描画されたボクセルの3辺寸法を取得（デバッグ用） */
  getLastVoxelDimensions(): { east: number; north: number; up: number } | undefined {
    return this._lastVoxelDimensions ? { ...this._lastVoxelDimensions } : undefined;
  }

  /**
   * WGS84 度数差から直接メートル距離を計算（テスト用）
   * 
   * 重要：GridLine() の lngUnit は既に cos(lat) を織り込んだ「実効度数差」
   * つまり、lngUnit = cos(lat) × 原始的な東西度数差
   */
  static getDistanceFromDegreesDifference(
    lat: number,
    latUnit: number,
    lngUnit: number
  ): { north: number; east: number } {
    const DEG_TO_M = 111000; // 1度 ≈ 111 km

    return {
      north: latUnit * DEG_TO_M,
      east: lngUnit * DEG_TO_M,  // lngUnit は既に cos 補正済みなので、そのまま使う
    };
  }

  /** VoxelSnapshot を更新して InstancedMesh に反映 */
  update(snapshot: VoxelSnapshot): void {
    let maxCount = 1;
    for (const [, state] of snapshot) {
      if (state.count > maxCount) maxCount = state.count;
    }

    let i = 0;
    const color = new THREE.Color();

    for (const [key, state] of snapshot) {
      if (i >= MAX_INSTANCES) break;

      // ── WGS84グリッドキー "ilat:ilng:ialt" をパース ──
      const parts = (key as string).split(":");
      const ilat = parseInt(parts[0], 10);
      const ilng = parseInt(parts[1], 10);
      const ialt = parseInt(parts[2], 10);
      if (isNaN(ilat) || isNaN(ilng) || isNaN(ialt)) continue;

      // ── セル中心の WGS84 座標 ──
      const lat = (ilat + 0.5) * this._latUnit;
      const lng = (ilng + 0.5) * this._lngUnit;
      const alt = (ialt + 0.5) * this._unitM;

      // ── センサーローカルに変換 ──
      const local = this._sensorTransformer.inverseTransformPoint(lat, lng, alt);

      // ── 隣接セル1（東側セル）の座標を計算 ──
      // 東西方向に隣接セル（lng + lngUnit）
      const latE = lat;
      const lngE = lng + this._lngUnit;
      const altE = alt;
      const localE = this._sensorTransformer.inverseTransformPoint(latE, lngE, altE);

      // ── 隣接セル2（北側セル）の座標を計算 ──
      // 南北方向に隣接セル（lat + latUnit）
      const latN = lat + this._latUnit;
      const lngN = lng;
      const altN = alt;
      const localN = this._sensorTransformer.inverseTransformPoint(latN, lngN, altN);

      // ── 隣接セルへの変位ベクトルから各軸スケールを算出 ──
      // heading 回転により East/North が sensor X/Y のどちらに対応するか変わるため
      // Euclidean (スカラー) ではなく、各軸の変位成分を直接使用する
      //
      // heading=0:  East→-sensorY, North→+sensorX  (R_sensor = Rz(90°))
      // heading=90: East→+sensorX, North→+sensorY  (R_sensor = Rz(0°))
      const dxEast  = localE.x - local.x;   // 東隣セルの sensor-X 変位
      const dyEast  = localE.y - local.y;   // 東隣セルの sensor-Y 変位
      const dxNorth = localN.x - local.x;   // 北隣セルの sensor-X 変位
      const dyNorth = localN.y - local.y;   // 北隣セルの sensor-Y 変位

      // 各 sensor 軸で支配的な変位成分を採用
      // → heading に依存せず、隙間・重なりなし
      const scaleX = Math.max(Math.abs(dxEast), Math.abs(dxNorth));
      const scaleY = Math.max(Math.abs(dyEast), Math.abs(dyNorth));
      const scaleZ = this._unitM;

      // Euclidean 距離も参照用に計算（ログ表示用）
      const distEast = Math.sqrt(dxEast ** 2 + dyEast ** 2);
      const distNorth = Math.sqrt(dxNorth ** 2 + dyNorth ** 2);

      // ── Three.js メッシュの配置 ──
      this._dummy.position.set(local.x, local.y, local.z);
      this._dummy.scale.set(scaleX, scaleY, scaleZ);
      this._dummy.updateMatrix();
      this._mesh.setMatrixAt(i, this._dummy.matrix);

      // 最初のボクセルのサイズを記録（デバッグ用）
      if (i === 0) {
        this._lastVoxelDimensions = {
          east: distEast,
          north: distNorth,
          up: scaleZ,
        };
        const ratio = distEast / distNorth;
        const percentDiff = ((1 - ratio) * 100).toFixed(1);
        console.log(
          `[GlobalVoxelRenderer] First voxel (vendor/alogs準拠): ` +
          `E=${distEast.toFixed(3)}m, N=${distNorth.toFixed(3)}m, U=${scaleZ.toFixed(3)}m, ` +
          `E/N=${ratio.toFixed(4)} (東西は南北より ${percentDiff}% 小さい)`
        );
        console.log(
          `[GlobalVoxelRenderer] Sensor軸スケール: ` +
          `scaleX=${scaleX.toFixed(4)} (dx_e=${dxEast.toFixed(4)}, dx_n=${dxNorth.toFixed(4)}), ` +
          `scaleY=${scaleY.toFixed(4)} (dy_e=${dyEast.toFixed(4)}, dy_n=${dyNorth.toFixed(4)})`
        );
      }

      // 密度に応じた色: 青(疎) → 赤(密)
      const t = Math.min(state.count / maxCount, 1);
      color.setHSL((1 - t) * 0.6, 1.0, 0.5);
      this._mesh.setColorAt(i, color);

      i++;
    }

    this._mesh.count = i;
    this._mesh.instanceMatrix.needsUpdate = true;
    if (this._mesh.instanceColor) this._mesh.instanceColor.needsUpdate = true;
  }

  dispose(): void {
    this._mesh.geometry.dispose();
    (this._mesh.material as THREE.Material).dispose();
  }
}
