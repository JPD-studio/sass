// viewer/tests/layers/frame-dispatcher.test.ts

import { describe, it, expect, beforeEach } from "@jest/globals";
import { FrameDispatcher } from "../../src/layers/frame-dispatcher.js";
import type { RenderLayer } from "../../src/layers/types.js";
import type { PointData } from "../../../ws-client/src/types.js";

/** テスト用のモック RenderLayer */
function createMockLayer(name: string): RenderLayer & { calls: PointData[][]; disposed: boolean } {
  const layer = {
    name,
    label: name,
    enabled: true,
    calls: [] as PointData[][],
    disposed: false,
    onFrame(points: PointData[], _frameId: number) {
      layer.calls.push(points);
    },
    setVisible(_visible: boolean) {},
    dispose() {
      layer.disposed = true;
    },
  };
  return layer;
}

describe("FrameDispatcher", () => {
  let dispatcher: FrameDispatcher;

  beforeEach(() => {
    dispatcher = new FrameDispatcher();
  });

  it("register したレイヤーに dispatch でフレームが配信される", () => {
    const layer = createMockLayer("test");
    dispatcher.register(layer);

    const points: PointData[] = [{ x: 1, y: 2, z: 3 }];
    dispatcher.dispatch(points);

    expect(layer.calls).toHaveLength(1);
    expect(layer.calls[0]).toBe(points);
    expect(dispatcher.frameId).toBe(1);
  });

  it("enabled=false のレイヤーには配信されない", () => {
    const layer = createMockLayer("test");
    layer.enabled = false;
    dispatcher.register(layer);

    dispatcher.dispatch([{ x: 0, y: 0, z: 0 }]);
    expect(layer.calls).toHaveLength(0);
  });

  it("toggle でレイヤーの enabled を切り替えられる", () => {
    const layer = createMockLayer("test");
    dispatcher.register(layer);

    expect(layer.enabled).toBe(true);
    dispatcher.toggle("test");
    expect(layer.enabled).toBe(false);
    dispatcher.toggle("test");
    expect(layer.enabled).toBe(true);
  });

  it("unregister でレイヤーが除去・dispose される", () => {
    const layer = createMockLayer("test");
    dispatcher.register(layer);

    dispatcher.unregister("test");
    expect(layer.disposed).toBe(true);
    expect(dispatcher.layers).toHaveLength(0);
  });

  it("onFrame が例外を投げても他のレイヤーは実行される", () => {
    const badLayer = createMockLayer("bad");
    badLayer.onFrame = () => {
      throw new Error("boom");
    };
    const goodLayer = createMockLayer("good");

    dispatcher.register(badLayer);
    dispatcher.register(goodLayer);

    dispatcher.dispatch([{ x: 0, y: 0, z: 0 }]);
    expect(goodLayer.calls).toHaveLength(1);
  });

  it("frameId は dispatch ごとにインクリメントされる", () => {
    dispatcher.dispatch([]);
    dispatcher.dispatch([]);
    dispatcher.dispatch([]);
    expect(dispatcher.frameId).toBe(3);
  });
});
