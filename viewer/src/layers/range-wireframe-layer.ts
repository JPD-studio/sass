// viewer/src/layers/range-wireframe-layer.ts

import * as THREE from "three";
import type { PointData } from "../../../ws-client/src/types.js";
import { BOX_CONFIG, CYLINDRICAL_CONFIG, FRUSTUM_CONFIG, POLYGON_CONFIG, SPHERICAL_CONFIG } from "./range-filter-config.js";
import type { RenderLayer } from "./types.js";

// --- 定数 ---

const WIREFRAME_SEGMENTS = 64;
const WIREFRAME_COLOR            = 0x00ff88; // フラスタム: 緑
const CYLINDRICAL_WIREFRAME_COLOR = 0x0088ff; // シリンドリカル: 青
const SPHERICAL_WIREFRAME_COLOR   = 0xff8800; // 球: オレンジ
const BOX_WIREFRAME_COLOR         = 0xffff00; // 直方体: 黄
const POLYGON_WIREFRAME_COLOR     = 0xff00ff; // 多角形: マゼンタ
const WIREFRAME_OPACITY = 0.6;
const GUIDE_LINE_COUNT = 8; // 上円と下円を繋ぐガイドライン本数
const SPHERICAL_LAT_LINES = 10;  // 球のラット線（緯度線）本数
const SPHERICAL_LON_LINES = 8;   // 球の経線（経度線）本数

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

function createCylindricalWireframe(
  radius: number,
  zMin: number,
  zMax: number,
): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({
    color: CYLINDRICAL_WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
  });

  // ① 底面の円（z = zMin）
  group.add(createCircle(radius, zMin, WIREFRAME_SEGMENTS, mat));

  // ② 上面の円（z = zMax）
  group.add(createCircle(radius, zMax, WIREFRAME_SEGMENTS, mat));

  // ③ 上下を繋ぐガイドライン
  for (let i = 0; i < GUIDE_LINE_COUNT; i++) {
    const theta = (i / GUIDE_LINE_COUNT) * Math.PI * 2;
    const x = radius * Math.cos(theta);
    const y = radius * Math.sin(theta);
    const geom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x, y, zMin),
      new THREE.Vector3(x, y, zMax),
    ]);
    group.add(new THREE.Line(geom, mat));
  }

  return group;
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

function createSphericalWireframe(
  radius: number,
  cx: number,
  cy: number,
  cz: number,
): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({
    color: SPHERICAL_WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
  });

  // ラット線 (Z 軍の円): 赤道・極近・中間各円
  for (let i = 0; i < SPHERICAL_LAT_LINES; i++) {
    const latFrac = i / (SPHERICAL_LAT_LINES - 1);
    const phi = latFrac * Math.PI; // 0(上極) → PI(下極)
    const r   = Math.sin(phi) * radius;
    const zOff = Math.cos(phi) * radius;
    if (r < 1e-4) continue;
    group.add(createCircle(r, cz + zOff, WIREFRAME_SEGMENTS, mat));
  }

  // 経線 (XZ・ YZ 平面の半円)
  for (let k = 0; k < SPHERICAL_LON_LINES; k++) {
    const angle = (k / SPHERICAL_LON_LINES) * Math.PI * 2;
    const verts: number[] = [];
    for (let i = 0; i <= WIREFRAME_SEGMENTS; i++) {
      const phi = (i / WIREFRAME_SEGMENTS) * Math.PI * 2;
      verts.push(
        cx + radius * Math.cos(phi) * Math.cos(angle),
        cy + radius * Math.cos(phi) * Math.sin(angle),
        cz + radius * Math.sin(phi),
      );
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    group.add(new THREE.Line(geom, mat));
  }

  group.position.set(cx, cy, 0); // cx/cy はサークル生成櫜に組み込み済みなのでオフセットは不要
  group.position.set(0, 0, 0);
  return group;
}

function createBoxWireframe(
  xMin: number, xMax: number,
  yMin: number, yMax: number,
  zMin: number, zMax: number,
): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({
    color: BOX_WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
  });

  // 直方体の 12 辺を描画
  const corners: [number, number, number][] = [
    [xMin, yMin, zMin], [xMax, yMin, zMin],
    [xMax, yMax, zMin], [xMin, yMax, zMin],
    [xMin, yMin, zMax], [xMax, yMin, zMax],
    [xMax, yMax, zMax], [xMin, yMax, zMax],
  ];
  const edges: [number, number][] = [
    [0,1],[1,2],[2,3],[3,0], // 底面
    [4,5],[5,6],[6,7],[7,4], // 上面
    [0,4],[1,5],[2,6],[3,7], // 垂直辺
  ];
  for (const [a, b] of edges) {
    const geom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(...corners[a]),
      new THREE.Vector3(...corners[b]),
    ]);
    group.add(new THREE.Line(geom, mat));
  }
  return group;
}

function createPolygonWireframe(
  vertices: readonly [number, number][],
  zMin: number,
  zMax: number,
): THREE.Group {
  const group = new THREE.Group();
  if (vertices.length < 3) return group;

  const mat = new THREE.LineBasicMaterial({
    color: POLYGON_WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
  });

  // 底面・上面のポリゴン (LineLoop)
  for (const z of [zMin, zMax]) {
    const verts: number[] = [];
    for (const [x, y] of vertices) verts.push(x, y, z);
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    group.add(new THREE.LineLoop(geom, mat));
  }

  // 各頂点を上下で繋ぐ垂直辺
  for (const [x, y] of vertices) {
    const geom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x, y, zMin),
      new THREE.Vector3(x, y, zMax),
    ]);
    group.add(new THREE.Line(geom, mat));
  }
  return group;
}

/** ジオメトリを安全に破棄してシーンから切り離す */
function disposeGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.Line) {
      obj.geometry.dispose();
      if (obj.material instanceof THREE.Material) obj.material.dispose();
    }
  });
  group.parent?.remove(group);
}

export class RangeWireframeLayer implements RenderLayer {
  readonly name = "range-wireframe";
  readonly label = "フィルター領域";
  enabled = true;

  private _scene: THREE.Scene;
  private _frustumGroup: THREE.Group;
  private _cylGroup: THREE.Group;
  private _sphGroup: THREE.Group;
  private _boxGroup: THREE.Group;
  private _polyGroup: THREE.Group;

  /** setVisible() から来るレイヤー全体の可視フラグ */
  private _layerVisible = true;
  private _frustumActive = true;
  private _cylActive = false;
  private _sphActive = false;
  private _boxActive = false;
  private _polyActive = false;

  /**
   * PointCloudLayer / VoxelLayer と異なり ViewerApp ではなく Scene を直接受け取る。
   * 理由: このレイヤーは ViewerApp のメソッド (updatePoints 等) を使わず、
   * Scene に静的ジオメトリを追加するだけのため。
   */
  constructor(scene: THREE.Scene) {
    this._scene = scene;

    // ── フラスタムワイヤーフレーム（フォールバック値で初期生成）──
    this._frustumGroup = new THREE.Group();
    this._frustumGroup.add(
      createFrustumWireframe(
        FRUSTUM_CONFIG.rBottom,
        FRUSTUM_CONFIG.rTop,
        FRUSTUM_CONFIG.height,
        FRUSTUM_CONFIG.zBottom,
      ),
    );
    scene.add(this._frustumGroup);

    // ── シリンドリカルワイヤーフレーム（フォールバック値で初期生成、filter_config まで非表示）──
    this._cylGroup = new THREE.Group();
    this._cylGroup.add(
      createCylindricalWireframe(
        CYLINDRICAL_CONFIG.radius,
        CYLINDRICAL_CONFIG.zMin,
        CYLINDRICAL_CONFIG.zMax,
      ),
    );
    this._cylGroup.visible = false;
    scene.add(this._cylGroup);

    // ── 球ワイヤーフレーム ──
    this._sphGroup = new THREE.Group();
    this._sphGroup.add(createSphericalWireframe(
      SPHERICAL_CONFIG.radius, SPHERICAL_CONFIG.cx, SPHERICAL_CONFIG.cy, SPHERICAL_CONFIG.cz,
    ));
    this._sphGroup.visible = false;
    scene.add(this._sphGroup);

    // ── 直方体ワイヤーフレーム ──
    this._boxGroup = new THREE.Group();
    this._boxGroup.add(createBoxWireframe(
      BOX_CONFIG.xMin, BOX_CONFIG.xMax,
      BOX_CONFIG.yMin, BOX_CONFIG.yMax,
      BOX_CONFIG.zMin, BOX_CONFIG.zMax,
    ));
    this._boxGroup.visible = false;
    scene.add(this._boxGroup);

    // ── 多角形ワイヤーフレーム（頂点が定まるまで非表示）──
    this._polyGroup = new THREE.Group();
    this._polyGroup.visible = false;
    scene.add(this._polyGroup);
  }

  /** filter_config.frustum でフラスタムワイヤーフレームを更新する */
  updateConfig(cfg: {
    r_bottom: number;
    r_top: number;
    height: number;
    z_bottom: number;
    active?: boolean;
    show_wireframe?: boolean;
  }): void {
    /**
     * ワイヤーフレーム表示ロジック（優先度順）:
     * 1️⃣ show_wireframe が明示的に指定 → それを使用（enabled 無視）
     * 2️⃣ show_wireframe なし → active を使用（後方互換）
     * 3️⃣ どちらもなし → デフォルト true（frustum は常時表示推奨）
     *
     * 例: "wireframe": true, "enabled": false → show_wireframe=true 送信 → 描画される
     */
    this._frustumActive = cfg.show_wireframe !== undefined ? cfg.show_wireframe : (cfg.active ?? true);

    disposeGroup(this._frustumGroup);
    this._frustumGroup = new THREE.Group();
    this._frustumGroup.add(
      createFrustumWireframe(cfg.r_bottom, cfg.r_top, cfg.height, cfg.z_bottom),
    );
    this._frustumGroup.visible = this._layerVisible && this._frustumActive;
    this._scene.add(this._frustumGroup);
    // デバッグ
    console.log(`[RangeWireframeLayer] frustum: visible=${this._frustumGroup.visible}, active=${this._frustumActive}, layerVisible=${this._layerVisible}, cfg.show_wireframe=${cfg.show_wireframe}, cfg.active=${cfg.active}`);  }

  /** filter_config.cylindrical でシリンドリカルワイヤーフレームを更新する */
  updateCylindricalConfig(cfg: {
    radius: number;
    z_min: number;
    z_max: number;
    active?: boolean;
    show_wireframe?: boolean;
  }): void {
    /**
     * ワイヤーフレーム表示ロジック（優先度順）:
     * 1️⃣ show_wireframe が明示的に指定 → それを使用（enabled 無視）
     * 2️⃣ show_wireframe なし → active を使用
     * 3️⃣ どちらもなし → デフォルト false（cylindrical は通常非表示）
     *
     * 例: "wireframe": true, "enabled": false → show_wireframe=true 送信 → 描画される
     * 例: "wireframe": false, "enabled": true → show_wireframe=false 送信 → 非表示
     */
    this._cylActive = cfg.show_wireframe ?? cfg.active ?? false;

    disposeGroup(this._cylGroup);
    this._cylGroup = new THREE.Group();
    this._cylGroup.add(
      createCylindricalWireframe(cfg.radius, cfg.z_min, cfg.z_max),
    );
    this._cylGroup.visible = this._layerVisible && this._cylActive;
    this._scene.add(this._cylGroup);

    // デバッグ
    console.log(`[RangeWireframeLayer] cylindrical: visible=${this._cylGroup.visible}, active=${this._cylActive}, layerVisible=${this._layerVisible}, cfg.show_wireframe=${cfg.show_wireframe}, cfg.active=${cfg.active}`);
  }

  /** filter_config.spherical で球ワイヤーフレームを更新する */
  updateSphericalConfig(cfg: {
    radius: number;
    cx: number;
    cy: number;
    cz: number;
    show_wireframe?: boolean;
    active?: boolean;
  }): void {
    this._sphActive = cfg.show_wireframe ?? cfg.active ?? false;
    disposeGroup(this._sphGroup);
    this._sphGroup = new THREE.Group();
    this._sphGroup.add(createSphericalWireframe(cfg.radius, cfg.cx, cfg.cy, cfg.cz));
    this._sphGroup.visible = this._layerVisible && this._sphActive;
    this._scene.add(this._sphGroup);
    console.log(`[RangeWireframeLayer] spherical: visible=${this._sphGroup.visible}`);
  }

  /** filter_config.box で直方体ワイヤーフレームを更新する */
  updateBoxConfig(cfg: {
    x_min: number; x_max: number;
    y_min: number; y_max: number;
    z_min: number; z_max: number;
    show_wireframe?: boolean;
    active?: boolean;
  }): void {
    this._boxActive = cfg.show_wireframe ?? cfg.active ?? false;
    disposeGroup(this._boxGroup);
    this._boxGroup = new THREE.Group();
    this._boxGroup.add(createBoxWireframe(cfg.x_min, cfg.x_max, cfg.y_min, cfg.y_max, cfg.z_min, cfg.z_max));
    this._boxGroup.visible = this._layerVisible && this._boxActive;
    this._scene.add(this._boxGroup);
    console.log(`[RangeWireframeLayer] box: visible=${this._boxGroup.visible}`);
  }

  /** filter_config.polygon で多角形ワイヤーフレームを更新する */
  updatePolygonConfig(cfg: {
    vertices: readonly [number, number][];
    z_min: number;
    z_max: number;
    show_wireframe?: boolean;
    active?: boolean;
  }): void {
    this._polyActive = (cfg.show_wireframe ?? cfg.active ?? false) && cfg.vertices.length >= 3;
    disposeGroup(this._polyGroup);
    this._polyGroup = new THREE.Group();
    if (cfg.vertices.length >= 3) {
      this._polyGroup.add(createPolygonWireframe(cfg.vertices, cfg.z_min, cfg.z_max));
    }
    this._polyGroup.visible = this._layerVisible && this._polyActive;
    this._scene.add(this._polyGroup);
    console.log(`[RangeWireframeLayer] polygon: visible=${this._polyGroup.visible}, vertices=${cfg.vertices.length}`);
  }

  /** 静的ジオメトリなのでフレームデータは使わない */
  onFrame(_points: PointData[], _frameId: number): void {
    // no-op: ワイヤーフレームはフレーム非依存
  }

  /**
   * レイヤーパネルの表示トグル。
   * 各フィルターの active 状態を保持しつつ、レイヤー全体を一括制御する。
   */
  setVisible(visible: boolean): void {
    this._layerVisible = visible;
    this._frustumGroup.visible = visible && this._frustumActive;
    this._cylGroup.visible    = visible && this._cylActive;
    this._sphGroup.visible    = visible && this._sphActive;
    this._boxGroup.visible    = visible && this._boxActive;
    this._polyGroup.visible   = visible && this._polyActive;
  }

  dispose(): void {
    disposeGroup(this._frustumGroup);
    disposeGroup(this._cylGroup);
    disposeGroup(this._sphGroup);
    disposeGroup(this._boxGroup);
    disposeGroup(this._polyGroup);
  }
}
