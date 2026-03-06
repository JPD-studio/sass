// viewer/tests/layers/range-wireframe-layer.test.ts

import { describe, it, expect } from "@jest/globals";
import { RangeWireframeLayer } from "../../src/layers/range-wireframe-layer.js";
import { Scene } from "three";

describe("RangeWireframeLayer", () => {
  it("Scene にグループを追加する", () => {
    const scene = new Scene();
    const layer = new RangeWireframeLayer(scene as any);
    // Scene.children にグループが追加されている
    expect((scene as any).children.length).toBeGreaterThan(0);
    expect(layer.name).toBe("range-wireframe");
    expect(layer.label).toBe("フィルター領域");
    expect(layer.enabled).toBe(true);
  });

  it("onFrame は no-op（例外を投げない）", () => {
    const scene = new Scene();
    const layer = new RangeWireframeLayer(scene as any);
    expect(() => layer.onFrame([], 1)).not.toThrow();
  });

  it("setVisible で visible を制御できる", () => {
    const scene = new Scene();
    const layer = new RangeWireframeLayer(scene as any);

    layer.setVisible(false);
    // 内部の group.visible が false
    expect((layer as any)._group.visible).toBe(false);

    layer.setVisible(true);
    expect((layer as any)._group.visible).toBe(true);
  });

  it("dispose で例外が発生しない", () => {
    const scene = new Scene();
    const layer = new RangeWireframeLayer(scene as any);
    expect(() => layer.dispose()).not.toThrow();
  });
});
