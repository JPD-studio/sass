import * as THREE from "three";
import type { VoxelSnapshot } from "../../../voxel/src/types.js";

const MAX_INSTANCES = 100_000;

export class VoxelRenderer {
  private _mesh: THREE.InstancedMesh;
  private _dummy = new THREE.Object3D();

  constructor(scene: THREE.Scene) {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshBasicMaterial({ color: 0x00ff88 });
    this._mesh = new THREE.InstancedMesh(geometry, material, MAX_INSTANCES);
    this._mesh.count = 0;
    scene.add(this._mesh);
  }

  update(snapshot: VoxelSnapshot): void {
    let i = 0;
    for (const [key] of snapshot) {
      if (i >= MAX_INSTANCES) break;
      const parts = key.split(":").map(Number);
      this._dummy.position.set(
        (parts[0] + 0.5),
        (parts[1] + 0.5),
        (parts[2] + 0.5)
      );
      this._dummy.updateMatrix();
      this._mesh.setMatrixAt(i, this._dummy.matrix);
      i++;
    }
    this._mesh.count = i;
    this._mesh.instanceMatrix.needsUpdate = true;
  }
}
