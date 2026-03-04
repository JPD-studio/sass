import * as THREE from "three";

export class SpatialIdRenderer {
  private _group: THREE.Group;

  constructor(scene: THREE.Scene) {
    this._group = new THREE.Group();
    scene.add(this._group);
  }

  update(_ids: string[]): void {
    // TODO: 空間 ID のグリッドラインを描画
  }
}
