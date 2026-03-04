// Three.js の最小モック（テスト用）
export class Scene {
  add() {}
  background = null;
}

export class PerspectiveCamera {
  position = { set() {} };
}

export class WebGLRenderer {
  domElement = { style: {} };
  setSize() {}
  render() {}
  dispose() {}
}

export class InstancedMesh {
  count = 0;
  instanceMatrix = { needsUpdate: false };
  setMatrixAt() {}
  constructor() {}
}

export class BoxGeometry {}
export class MeshBasicMaterial {}
export class SpriteMaterial {}
export class Sprite {
  position = { set() {} };
  scale = { set() {} };
  constructor() {}
}
export class AmbientLight {}
export class Color {}
export class Object3D {
  position = { set() {} };
  matrix = {};
  updateMatrix() {}
}
export class Group {}
