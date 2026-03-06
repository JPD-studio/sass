// Three.js の最小モック（テスト用）
export class Scene {
  children = [];
  add(obj) { this.children.push(obj); }
  remove(obj) { this.children = this.children.filter(c => c !== obj); }
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
  visible = true;
  instanceMatrix = { needsUpdate: false };
  instanceColor = { needsUpdate: false };
  setMatrixAt() {}
  setColorAt() {}
  constructor() {}
}

export class BoxGeometry {}
export class MeshStandardMaterial {}
export class MeshBasicMaterial {}
export class SpriteMaterial {}
export class Sprite {
  position = { set() {} };
  scale = { set() {} };
  constructor() {}
}
export class AmbientLight {}
export class Color {
  r = 0; g = 0; b = 0;
  setHSL() { return this; }
}
export class Object3D {
  position = { set() {} };
  scale = { setScalar() {} };
  matrix = {};
  updateMatrix() {}
}
export class Group {
  visible = true;
  parent = null;
  children = [];
  add(obj) { this.children.push(obj); obj.parent = this; }
  traverse(fn) {
    fn(this);
    for (const c of this.children) {
      if (c.traverse) c.traverse(fn);
      else fn(c);
    }
  }
}

export class BufferGeometry {
  setAttribute() { return this; }
  setFromPoints() { return this; }
  dispose() {}
}

export class BufferAttribute {
  needsUpdate = false;
  constructor() {}
  setUsage() { return this; }
}

export class Float32BufferAttribute extends BufferAttribute {}

export class InstancedBufferAttribute extends BufferAttribute {}

export class LineBasicMaterial {
  dispose() {}
  constructor() {}
}
export class PointsMaterial {}
export class Material {
  dispose() {}
}

export class LineLoop {
  geometry = new BufferGeometry();
  material = new LineBasicMaterial();
  parent = null;
  traverse(fn) { fn(this); }
}

export class Line {
  geometry = new BufferGeometry();
  material = new LineBasicMaterial();
  parent = null;
  traverse(fn) { fn(this); }
}

export class LineSegments {}

export class Points {
  geometry = new BufferGeometry();
  visible = true;
}

export class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
}

export class AxesHelper {}

export const DynamicDrawUsage = 35048;
export const DoubleSide = 2;
