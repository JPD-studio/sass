// viewer/src/layers/range-wireframe-layer.ts

import * as THREE from "three";
import type { PointData } from "../../../ws-client/src/types.js";
import { FRUSTUM_CONFIG } from "./range-filter-config.js";
import type { RenderLayer } from "./types.js";

// --- 定数 ---

const WIREFRAME_SEGMENTS = 64;
const WIREFRAME_COLOR = 0x00ff88;
const WIREFRAME_OPACITY = 0.6;
const GUIDE_LINE_COUNT = 8; // 上円と下円を繋ぐガイドライン本数

// --- 内部ヘルパー ---

function createCircle(
  radius: number,
  z: number,
  segments: number,
  material: THREE.LineBasicMaterial,
): THREE.LineLoop {
  const verts: number[] = [];
  // LineLoop は自動で閉路を生成するため i < segments で十分（重複頂点を避ける）
  for (let i = 0; i < segments; i++) {
    const theta = (i / segments) * Math.PI * 2;
    verts.push(radius * Math.cos(theta), radius * Math.sin(theta), z);
  }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(verts, 3),
  );
  return new THREE.LineLoop(geom, material);
}

function createFrustumWireframe(
  rBottom: number,
  rTop: number,
  height: number,
  zBottom: number,
): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({
    color: WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
  });

  // ① 底面の円（z = zBottom）
  group.add(createCircle(rBottom, zBottom, WIREFRAME_SEGMENTS, mat));

  // ② 上面の円（z = zBottom + height）
  group.add(createCircle(rTop, zBottom + height, WIREFRAME_SEGMENTS, mat));

  // ③ 上下を繋ぐガイドライン
  for (let i = 0; i < GUIDE_LINE_COUNT; i++) {
    const theta = (i / GUIDE_LINE_COUNT) * Math.PI * 2;
    const x0 = rBottom * Math.cos(theta);
    const y0 = rBottom * Math.sin(theta);
    const x1 = rTop * Math.cos(theta);
    const y1 = rTop * Math.sin(theta);

    const geom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x0, y0, zBottom),
      new THREE.Vector3(x1, y1, zBottom + height),
    ]);
    group.add(new THREE.Line(geom, mat));
  }

  return group;
}

// --- RangeWireframeLayer ---

export class RangeWireframeLayer implements RenderLayer {
  readonly name = "range-wireframe";
  readonly label = "フィルター領域";
  enabled = true;

  private _group: THREE.Group;

  /**
   * PointCloudLayer / VoxelLayer と異なり ViewerApp ではなく Scene を直接受け取る。
   * 理由: このレイヤーは ViewerApp のメソッド (updatePoints 等) を使わず、
   * Scene に静的ジオメトリを追加するだけのため。
   */
  constructor(scene: THREE.Scene) {
    this._group = new THREE.Group();

    // フラスタム（円錐台）ワイヤーフレームを生成
    const wireframe = createFrustumWireframe(
      FRUSTUM_CONFIG.rBottom,
      FRUSTUM_CONFIG.rTop,
      FRUSTUM_CONFIG.height,
      FRUSTUM_CONFIG.zBottom,
    );
    this._group.add(wireframe);

    scene.add(this._group);
  }

  /** 静的ジオメトリなのでフレームデータは使わない */
  onFrame(_points: PointData[], _frameId: number): void {
    // no-op: ワイヤーフレームはフレーム非依存
  }

  setVisible(visible: boolean): void {
    this._group.visible = visible;
  }

  dispose(): void {
    // GPU リソース（Geometry / Material）を解放してメモリリーク防止
    this._group.traverse((obj) => {
      if (obj instanceof THREE.Line) {
        // THREE.LineLoop extends THREE.Line なのでこの1条件で両方カバーされる
        obj.geometry.dispose();
        if (obj.material instanceof THREE.Material) obj.material.dispose();
      }
    });
    this._group.parent?.remove(this._group);
  }
}
