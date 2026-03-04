/**
 * spatial-id-converter.ts
 *
 * vendor/alogs/ は CommonJS 形式のため ESM パッケージから直接 import できない。
 * このファイルはスタブ実装。実際の変換ロジックは TODO。
 */

export interface SpatialPoint {
  lat: number;
  lng: number;
  alt: number;
}

/**
 * 緯度経度高度を空間 ID 文字列に変換する（スタブ）
 * TODO: vendor/alogs/Encode.js の Encode.LatLngTo3DID を利用する
 */
export function pointToSpatialId(
  _point: SpatialPoint,
  _unit?: number
): string {
  // TODO: implement using vendor/alogs/Encode.LatLngTo3DID
  return "";
}

/**
 * 空間 ID 文字列を緯度経度高度に逆変換する（スタブ）
 * TODO: vendor/alogs/Decode.js の Decode.gridIdTo3DLocation を利用する
 */
export function spatialIdToPoint(_id: string): SpatialPoint {
  // TODO: implement using vendor/alogs/Decode.gridIdTo3DLocation
  return { lat: 0, lng: 0, alt: 0 };
}
