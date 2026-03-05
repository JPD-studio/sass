import * as THREE from "three";
import type { VoxelSnapshot } from "../../../voxel/src/types.js";

const MAX_INSTANCES = 100_000;

export class VoxelRenderer {
  private _mesh: THREE.InstancedMesh;
  private _dummy = new THREE.Object3D();

  constructor(scene: THREE.Scene) {
    const geometry = new THREE.BoxGeometry(1, 1, 1);  // scale で cellSize に合わせる
    const material = new THREE.MeshStandardMaterial({
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide,
    });
    this._mesh = new THREE.InstancedMesh(geometry, material, MAX_INSTANCES);
    this._mesh.instanceColor = new THREE.InstancedBufferAttribute(
      new Float32Array(MAX_INSTANCES * 3), 3
    );
    this._mesh.count = 0;
    scene.add(this._mesh);
  }

  update(snapshot: VoxelSnapshot, cellSize = 1.0): void {
    // 最大カウントを計算（密度カラー用）
    let maxCount = 1;
    for (const [, state] of snapshot) {
      if (state.count > maxCount) maxCount = state.count;
    }

    let i = 0;
    const color = new THREE.Color();
    for (const [key, state] of snapshot) {
      if (i >= MAX_INSTANCES) break;
      const parts = key.split(":").map(Number);
      // floor(v/cellSize)*cellSize + cellSize/2 = セル中心 (負の Z 空間でも正確)
      this._dummy.position.set(
        (parts[0] + 0.5) * cellSize,
        (parts[1] + 0.5) * cellSize,
        (parts[2] + 0.5) * cellSize
      );
      this._dummy.scale.setScalar(cellSize);
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
}
