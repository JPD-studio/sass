import * as THREE from "three";

export class DroneSprite {
  private _sprite: THREE.Sprite;

  constructor(scene: THREE.Scene) {
    const material = new THREE.SpriteMaterial({ color: 0xffff00 });
    this._sprite = new THREE.Sprite(material);
    this._sprite.scale.set(2, 2, 1);
    scene.add(this._sprite);
  }

  setPosition(x: number, y: number, z: number): void {
    this._sprite.position.set(x, y, z);
  }
}
