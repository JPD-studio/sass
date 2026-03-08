/**
 * global-voxel-renderer.ts
 *
 * ENU グリッドキー ("ie:in:iu") をもつ VoxelSnapshot を Three.js InstancedMesh で描画する。
 *
 * 処理フロー:
 *   キー "ie:in:iu"
 *     → ENU セル中心 (ie+0.5, in+0.5, iu+0.5) × unitM  [m from グリッド原点]
 *     → gridTransformer.transformPoint()  → WGS84
 *     → sensorTransformer.inverseTransformPoint() → センサーローカル XYZ
 *     → InstancedMesh の位置に反映
 */

import * as THREE from "three";
import type { CoordinateTransformer } from "../../../spatial-grid/src/coordinate-transform.js";
import type { VoxelSnapshot } from "../../../voxel/src/types.js";

const MAX_INSTANCES = 50_000;

export class GlobalVoxelRenderer {
  private readonly _mesh: THREE.InstancedMesh;
  private readonly _dummy = new THREE.Object3D();
  private readonly _unitM: number;
  private readonly _gridTransformer: CoordinateTransformer;
  private readonly _sensorTransformer: CoordinateTransformer;

  constructor(
    scene: THREE.Scene,
    unitM: number,
    gridTransformer: CoordinateTransformer,
    sensorTransformer: CoordinateTransformer,
  ) {
    this._unitM = unitM;
    this._gridTransformer = gridTransformer;
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

      // ENU グリッドキー "ie:in:iu" → セル中心の ENU 座標 [m from グリッド原点]
      const parts = (key as string).split(":");
      const ie  = parseInt(parts[0], 10);
      const in_ = parseInt(parts[1], 10);
      const iu  = parseInt(parts[2], 10);
      if (isNaN(ie) || isNaN(in_) || isNaN(iu)) continue;

      const e = (ie + 0.5) * this._unitM;
      const n = (in_ + 0.5) * this._unitM;
      const u = (iu + 0.5) * this._unitM;

      // ENU (グリッド原点基準) → WGS84
      // gridTransformer は heading=90 (R_sensor=I) なので transformPoint(e,n,u) = ENU → WGS84
      const wgs84 = this._gridTransformer.transformPoint(e, n, u);

      // WGS84 → センサーローカル XYZ
      // inverseTransformPoint は Z-up 規約で返す → camera.up.set(0,0,1) の Three.js と一致
      const local = this._sensorTransformer.inverseTransformPoint(wgs84.lat, wgs84.lng, wgs84.alt);
      this._dummy.position.set(local.x, local.y, local.z);
      this._dummy.scale.setScalar(this._unitM);
      this._dummy.updateMatrix();
      this._mesh.setMatrixAt(i, this._dummy.matrix);

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
