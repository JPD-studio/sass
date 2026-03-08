import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { VoxelSnapshot } from "../../voxel/src/types.js";
import { VoxelRenderer } from "./renderers/voxel-renderer.js";
import type { PointData } from "../../ws-client/src/types.js";

// カメラ状態（同期用）
export interface CameraState {
  position: { x: number; y: number; z: number };
  target: { x: number; y: number; z: number };
  up: { x: number; y: number; z: number };
}

export class ViewerApp {
  private _scene: THREE.Scene;
  private _camera: THREE.PerspectiveCamera;
  private _renderer: THREE.WebGLRenderer;
  private _voxelRenderer: VoxelRenderer;
  private _controls: OrbitControls;
  private _animationId: number | null = null;

  // 生の点群を Points で描画
  private _pointCloud: THREE.Points;
  private _positions: Float32Array;
  private _pointColors: Float32Array;
  private _pointCount = 0;
  private static readonly MAX_POINTS = 200_000;

  constructor(
    container: HTMLElement,
    coinConfig?: {
      position: [number, number, number];
      radius_m?: number;
      height_m?: number;
      rotation?: { x?: number; y?: number; z?: number };
    },
    onCameraChange?: (state: CameraState) => void
  ) {
    this._scene = new THREE.Scene();
    this._scene.background = new THREE.Color(0x111111);

    this._camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    // Ouster は Z-up 座標系 → Three.js のデフォルト Y-up から変更
    this._camera.up.set(0, 0, 1);
    this._camera.position.set(0, -20, 20);

    this._renderer = new THREE.WebGLRenderer({ antialias: true });
    this._renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(this._renderer.domElement);

    // OrbitControls（マウスで回転・ズーム・パン）
    this._controls = new OrbitControls(this._camera, this._renderer.domElement);
    this._controls.screenSpacePanning = false;

    // カメラ同期コールバック（split-view時のみ設定される）
    if (onCameraChange) {
      this._controls.addEventListener('change', () => {
        onCameraChange(this.getCameraState());
      });
    }

    // 照明
    this._scene.add(new THREE.AmbientLight(0xffffff, 1));

    // 座標軸ヘルパー（XYZ 100m）
    this._scene.add(new THREE.AxesHelper(100));

    // 同心円グリッド（10m 間隔、最大 100m）
    this._addConcentricCircles(100, 10, 0xffffff);

    // 方位ラベル（東西南北上下）
    this._addDirectionLabels(10);

    // コイン型オブジェクト（config.json から読み込み）
    if (coinConfig?.position) {
      const [x, y, z] = coinConfig.position;
      const radius = coinConfig.radius_m ?? 0.35;
      const height = coinConfig.height_m ?? 0.5;
      const rotation = coinConfig.rotation ?? { x: 0, y: 0, z: 0 };
      this._addCoinObject(x, y, z, radius, height, rotation);
    }

    // ---- 点群 (Points) ----
    this._positions = new Float32Array(ViewerApp.MAX_POINTS * 3);
    this._pointColors = new Float32Array(ViewerApp.MAX_POINTS * 3);

    const geom = new THREE.BufferGeometry();
    geom.setAttribute(
      "position",
      new THREE.BufferAttribute(this._positions, 3).setUsage(THREE.DynamicDrawUsage)
    );
    geom.setAttribute(
      "color",
      new THREE.BufferAttribute(this._pointColors, 3).setUsage(THREE.DynamicDrawUsage)
    );

    const mat = new THREE.PointsMaterial({
      size: 0.05,
      vertexColors: true,
    });
    this._pointCloud = new THREE.Points(geom, mat);
    this._scene.add(this._pointCloud);

    // ---- ボクセル半透明 ----
    this._voxelRenderer = new VoxelRenderer(this._scene);

    // リサイズ対応
    window.addEventListener("resize", () => {
      this._camera.aspect = container.clientWidth / container.clientHeight;
      this._camera.updateProjectionMatrix();
      this._renderer.setSize(container.clientWidth, container.clientHeight);
    });
  }

  /** 生の点群を直接描画（ouster_bridge3 同等のライン表示） */
  updatePoints(points: PointData[]): void {
    const n = Math.min(points.length, ViewerApp.MAX_POINTS);
    for (let i = 0; i < n; i++) {
      const p = points[i];
      this._positions[i * 3] = p.x;
      this._positions[i * 3 + 1] = p.y;
      this._positions[i * 3 + 2] = -p.z; // センサーフレームの Z は下向き → 反転

      // 距離に応じた色: 近い=青、遠い=赤（HSL）
      const dist = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
      const t = Math.min(dist / 50, 1); // 0m=青, 50m=赤
      const color = new THREE.Color();
      color.setHSL((1 - t) * 0.6, 1.0, 0.5);
      this._pointColors[i * 3] = color.r;
      this._pointColors[i * 3 + 1] = color.g;
      this._pointColors[i * 3 + 2] = color.b;
    }
    this._pointCount = n;

    const geom = this._pointCloud.geometry;
    geom.setDrawRange(0, n);
    (geom.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    (geom.attributes.color as THREE.BufferAttribute).needsUpdate = true;
  }

  // --- カメラ同期メソッド（split-view 用） ---

  /** 現在のカメラ状態を取得 */
  getCameraState(): CameraState {
    return {
      position: { x: this._camera.position.x, y: this._camera.position.y, z: this._camera.position.z },
      target: { x: this._controls.target.x, y: this._controls.target.y, z: this._controls.target.z },
      up: { x: this._camera.up.x, y: this._camera.up.y, z: this._camera.up.z },
    };
  }

  /** カメラ状態を適用（他方の画面から同期される） */
  setCameraState(state: CameraState): void {
    this._camera.position.set(state.position.x, state.position.y, state.position.z);
    this._controls.target.set(state.target.x, state.target.y, state.target.z);
    this._camera.up.set(state.up.x, state.up.y, state.up.z);
    this._camera.updateProjectionMatrix();
    this._controls.update();
  }

  // --- public getters for RenderLayer access ---

  /** Three.js Scene（RangeWireframeLayer が静的ジオメトリを追加するために使用） */
  get scene(): THREE.Scene {
    return this._scene;
  }

  /** 点群 Points オブジェクト（PointCloudLayer が visible 制御に使用） */
  get pointCloudObject(): THREE.Points {
    return this._pointCloud;
  }

  /** ボクセル InstancedMesh（VoxelLayer が visible 制御に使用） */
  get voxelObject(): THREE.InstancedMesh {
    return this._voxelRenderer.mesh;
  }

  updateVoxels(snapshot: VoxelSnapshot, cellSize = 1.0): void {
    this._voxelRenderer.update(snapshot, cellSize);
  }

  render(): void {
    const loop = () => {
      this._animationId = requestAnimationFrame(loop);
      this._controls.update();
      this._renderer.render(this._scene, this._camera);
    };
    loop();
  }

  dispose(): void {
    if (this._animationId !== null) {
      cancelAnimationFrame(this._animationId);
      this._animationId = null;
    }
    this._renderer.dispose();
  }

  /** 同心円グリッド（ouster_bridge3 同等） */
  private _addConcentricCircles(
    maxRadius: number,
    interval: number,
    color: number
  ): void {
    for (let r = interval; r <= maxRadius; r += interval) {
      const segments = 128;
      const verts: number[] = [];
      for (let i = 0; i <= segments; i++) {
        const theta = (i / segments) * 2 * Math.PI;
        verts.push(r * Math.cos(theta), r * Math.sin(theta), 0);
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(verts, 3)
      );
      const mat = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity: 0.3,
      });
      this._scene.add(new THREE.LineLoop(geom, mat));

      // 距離ラベル
      this._addDistanceLabel(`${r}m`, r, 0, 0);
    }
  }

  /** テキストスプライトでラベルを追加 */
  private _addDistanceLabel(
    text: string,
    x: number,
    y: number,
    z: number
  ): void {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    ctx.font = "28px sans-serif";
    ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
    ctx.fillText(text, 10, 40);

    const texture = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(mat);
    sprite.position.set(x, y, z);
    sprite.scale.set(5, 1.25, 1);
    this._scene.add(sprite);
  }

  /** 方向ラベル（東西南北上下）を追加 */
  private _addDirectionLabels(distance: number): void {
    // 東西（X軸）
    this._addDirectionLabel("E", distance, 0, 0, 0xff4444); // Red tone
    this._addDirectionLabel("W", -distance, 0, 0, 0xff4444);
    
    // 南北（Y軸）
    this._addDirectionLabel("N", 0, distance, 0, 0x44ff44); // Green tone
    this._addDirectionLabel("S", 0, -distance, 0, 0x44ff44);
    
    // 上下（Z軸）
    this._addDirectionLabel("Up", 0, 0, distance, 0x4444ff); // Blue tone
    this._addDirectionLabel("Down", 0, 0, -distance, 0x4444ff);
  }

  /** 方向ラベルをカラー付きで追加 */
  private _addDirectionLabel(
    text: string,
    x: number,
    y: number,
    z: number,
    color: number
  ): void {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    ctx.font = "bold 32px sans-serif";
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 3;
    ctx.strokeText(text, 10, 45);
    ctx.fillText(text, 10, 45);

    const texture = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(mat);
    sprite.position.set(x, y, z);
    sprite.scale.set(5, 1.25, 1);
    this._scene.add(sprite);
  }

  /** コイン型オブジェクトを追加（塗りつぶし赤 + ワイヤーフレーム） */
  private _addCoinObject(
    x: number,
    y: number,
    z: number,
    radius: number,
    height: number,
    rotation: { x?: number; y?: number; z?: number } = {}
  ): void {
    // 円盤形状（円柱、上下半径同じ）
    const geometry = new THREE.CylinderGeometry(radius, radius, height, 64);
    
    // 塗りつぶし：真っ赤
    const fillMaterial = new THREE.MeshStandardMaterial({
      color: 0xFF0000,        // 真っ赤
      metalness: 0.3,
      roughness: 0.7,
    });
    
    const coin = new THREE.Mesh(geometry, fillMaterial);
    coin.position.set(x, y, z);
    
    // 回転を適用
    const rotX = rotation.x ?? 0;
    const rotY = rotation.y ?? 0;
    const rotZ = rotation.z ?? 0;
    coin.rotation.order = 'XYZ';
    coin.rotation.x = rotX;
    coin.rotation.y = rotY;
    coin.rotation.z = rotZ;
    
    coin.castShadow = true;
    coin.receiveShadow = true;
    
    this._scene.add(coin);
    
    // ワイヤーフレーム線を追加
    const edges = new THREE.EdgesGeometry(geometry);
    const wireframe = new THREE.LineSegments(
      edges,
      new THREE.LineBasicMaterial({ color: 0xFFFFFF, linewidth: 2 })
    );
    wireframe.position.copy(coin.position);
    wireframe.rotation.copy(coin.rotation);
    
    this._scene.add(wireframe);
  }
}
