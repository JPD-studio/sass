import { describe, it, expect } from "@jest/globals";
import {
  pointToSpatialId,
  spatialIdToPoint,
} from "../src/spatial-id-converter.js";

describe("spatial-id-converter (stub)", () => {
  it("pointToSpatialId は文字列を返す", () => {
    const result = pointToSpatialId({ lat: 35.6812, lng: 139.7671, alt: 10 });
    expect(typeof result).toBe("string");
  });

  it("spatialIdToPoint はオブジェクトを返す", () => {
    const result = spatialIdToPoint("some-id");
    expect(typeof result.lat).toBe("number");
    expect(typeof result.lng).toBe("number");
    expect(typeof result.alt).toBe("number");
  });

  it("unit オプションを渡しても例外が発生しない", () => {
    expect(() =>
      pointToSpatialId({ lat: 35.0, lng: 135.0, alt: 0 }, 1)
    ).not.toThrow();
  });
});
