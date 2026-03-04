import * as THREE from "three";
import type { VoxelSnapshot } from "../../voxel/src/types.js";
import { VoxelRenderer } from "./renderers/voxel-renderer.js";

export class ViewerApp {
  private _scene: THREE.Scene;
  private _camera: THREE.PerspectiveCamera;
  private _renderer: THREE.WebGLRenderer;
  private _voxelRenderer: VoxelRenderer;
  private _animationId: number | null = null;

  constructor(container: HTMLElement) {
    this._scene = new THREE.Scene();
    this._scene.background = new THREE.Color(0x111111);

    this._camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    this._camera.position.set(0, 0, 50);

    this._renderer = new THREE.WebGLRenderer({ antialias: true });
    this._renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(this._renderer.domElement);

    // 環境光
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    this._scene.add(ambientLight);

    this._voxelRenderer = new VoxelRenderer(this._scene);
  }

  updateVoxels(snapshot: VoxelSnapshot): void {
    this._voxelRenderer.update(snapshot);
  }

  render(): void {
    const loop = () => {
      this._animationId = requestAnimationFrame(loop);
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
}
