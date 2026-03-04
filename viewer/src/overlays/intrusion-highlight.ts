import * as THREE from "three";

export class IntrusionHighlight {
  private _mesh: THREE.InstancedMesh;
  private _dummy = new THREE.Object3D();

  constructor(scene: THREE.Scene) {
    const geometry = new THREE.BoxGeometry(1.05, 1.05, 1.05);
    const material = new THREE.MeshBasicMaterial({
      color: 0xff0000,
      transparent: true,
      opacity: 0.5,
      wireframe: true,
    });
    this._mesh = new THREE.InstancedMesh(geometry, material, 10_000);
    this._mesh.count = 0;
    scene.add(this._mesh);
  }

  update(keys: string[]): void {
    let i = 0;
    for (const key of keys) {
      if (i >= 10_000) break;
      const parts = key.split(":").map(Number);
      this._dummy.position.set(parts[0] + 0.5, parts[1] + 0.5, parts[2] + 0.5);
      this._dummy.updateMatrix();
      this._mesh.setMatrixAt(i, this._dummy.matrix);
      i++;
    }
    this._mesh.count = i;
    this._mesh.instanceMatrix.needsUpdate = true;
  }
}
