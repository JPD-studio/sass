// ws-client/tests/ws-connection.test.ts
import { describe, it, expect } from "@jest/globals";
import { WsConnection } from "../src/ws-connection.js";
import { PointStream } from "../src/point-stream.js";
import type { ConnectionConfig } from "../src/types.js";

const config: ConnectionConfig = {
  url: "ws://127.0.0.1:9999",
  reconnectInterval: 100,
  maxRetries: 0,
};

describe("WsConnection", () => {
  it("インスタンスを生成できる", () => {
    const conn = new WsConnection(config);
    expect(conn).toBeDefined();
  });

  it("初期状態で isConnected() が false", () => {
    const conn = new WsConnection(config);
    expect(conn.isConnected()).toBe(false);
  });

  it("connect() 前に disconnect() を呼んでも例外なし", () => {
    const conn = new WsConnection(config);
    expect(() => conn.disconnect()).not.toThrow();
  });

  it("onMessage でコールバックを登録できる", () => {
    const conn = new WsConnection(config);
    expect(() => conn.onMessage((_pts) => {})).not.toThrow();
  });

  it("frames() が AsyncGenerator を返す", () => {
    const conn = new WsConnection(config);
    const gen = conn.frames();
    // AsyncGenerator は Symbol.asyncIterator を持つ
    expect(typeof gen[Symbol.asyncIterator]).toBe("function");
  });

  it("disconnect() 後に frames() が即座に完了する", async () => {
    const conn = new WsConnection(config);
    const gen = conn.frames();
    conn.disconnect();
    const result = await gen.next();
    expect(result.done).toBe(true);
  });
});

describe("PointStream", () => {
  it("addSource / removeSource が例外なし", () => {
    const stream = new PointStream();
    const conn = new WsConnection(config);
    expect(() => stream.addSource("a", conn)).not.toThrow();
    expect(() => stream.removeSource("a")).not.toThrow();
  });

  it("mergedFrames() が AsyncGenerator を返す", () => {
    const stream = new PointStream();
    const gen = stream.mergedFrames();
    expect(typeof gen[Symbol.asyncIterator]).toBe("function");
  });
});
