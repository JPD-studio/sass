import { describe, it, expect } from "@jest/globals";
import { VoxelRenderer } from "../src/renderers/voxel-renderer.js";
import { Scene } from "three";

describe("VoxelRenderer", () => {
  it("Three.Scene を受け取ってインスタンスを生成できる", () => {
    const scene = new Scene();
    const renderer = new VoxelRenderer(scene);
    expect(renderer).toBeDefined();
  });

  it("update() を呼んでも例外が発生しない", () => {
    const scene = new Scene();
    const renderer = new VoxelRenderer(scene);
    const snap = new Map([
      ["0:0:0", { count: 5, lastUpdated: 1 }],
      ["1:2:3", { count: 3, lastUpdated: 2 }],
    ]);
    expect(() => renderer.update(snap)).not.toThrow();
  });
});
