/**
 * spatial-id-converter.ts
 * ALoGS ライブラリの ESM ラッパー（ユーティリティ関数群）
 *
 * vendor/ に直置きされた CJS モジュールを createRequire() で呼び出す。
 * vendor/alogs/ はコピーせず、リポジトリ内の現在位置をそのまま参照。
 *
 * Phase 3a の GlobalVoxelGrid がこれらを使用する。
 *
 * ⚠️ Node.js 専用 — ブラウザ (webpack) からは使用不可
 *    createRequire は Node.js API のため、geo-viewer から import してはならない。
 */

import { createRequire } from "module";
import type { IGrid3D } from "../../vendor/models/Model.js";

const _require = createRequire(import.meta.url);

// vendor/alogs/*.js は CJS (require("../util/Util") 等の相対参照あり)
// createRequire で読み込めば Node.js が CJS として正しく解決する
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Encode = _require("../../vendor/alogs/Encode.js").default as any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Decode = _require("../../vendor/alogs/Decode.js").default as any;

/**
 * WGS84 座標 → ALoGS 空間ID 文字列
 * @param lat  WGS84 緯度 [度]
 * @param lng  WGS84 経度 [度]
 * @param alt  WGS84 楕円体高 [m]
 * @param unit_m グリッドサイズ [m]
 */
export function pointToSpatialId(
  lat: number,
  lng: number,
  alt: number,
  unit_m: number
): string {
  return Encode.LatLngTo3DID(lat, lng, alt, unit_m) as string;
}

/**
 * ALoGS 空間ID → グリッド境界情報
 */
export function spatialIdToBounds(spatialId: string): IGrid3D {
  return Decode.gridIdTo3DLocation(spatialId) as IGrid3D;
}

/**
 * ALoGS 空間ID → グリッド中心座標 (WGS84)
 */
export function spatialIdToCenter(spatialId: string): {
  lat: number;
  lng: number;
  alt: number;
} {
  const bounds: IGrid3D = spatialIdToBounds(spatialId);
  return {
    lat: (bounds.bounds.north + bounds.bounds.south) / 2,
    lng: (bounds.bounds.east + bounds.bounds.west) / 2,
    alt: (bounds.altitude.upper + bounds.altitude.lower) / 2,
  };
}
