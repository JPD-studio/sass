// viewer/src/layers/range-filter-config.ts

/**
 * Python 側 cepf_sdk/filters/range/ の形状定数を TypeScript 側にミラー。
 * 現在はハードコード。将来は共通 JSON 設定ファイルから読み込む。
 *
 * ⚠ 変更時は Python 側の対応ファイルも手動で同期すること。
 *  - frustum → cepf_sdk/filters/range/frustum.py
 *  - cylindrical → cepf_sdk/filters/range/cylindrical.py
 *  - box → cepf_sdk/filters/range/box.py
 *  - spherical → cepf_sdk/filters/range/spherical.py
 *  - polygon → cepf_sdk/filters/range/polygon.py
 */

// ---- FrustumFilter（円錐台）— 現在のアクティブフィルター ----
export const FRUSTUM_CONFIG = {
  rBottom: 1.775, // LiDAR 高さ（z=0）での半径 [m]
  rTop: 2.5, // z=+30m での半径 [m]
  height: 32.0, // 円錐台の高さ [m] — Python 側 (frustum.py) と同期
  zBottom: -20.0, // 底面 Z 座標 [m] — Python 側 (frustum.py) と同期
} as const;

// ---- CylindricalFilter（円柱）— 広域クリッピング ----
export const CYLINDRICAL_CONFIG = {
  radius: 50.0, // 水平半径 [m]
  zMin: -20.0, // Z 下限 [m]
  zMax: 30.0, // Z 上限 [m]
  cx: 0.0, // 中心 X [m]
  cy: 0.0, // 中心 Y [m]
} as const;

// ---- BoxFilter（直方体）----
export const BOX_CONFIG = {
  xMin: -25.0,
  xMax:  25.0,
  yMin: -25.0,
  yMax:  25.0,
  zMin: -20.0,
  zMax:  30.0,
} as const;

// ---- SphericalFilter（球）----
export const SPHERICAL_CONFIG = {
  radius: 30.0,
  cx: 0.0,
  cy: 0.0,
  cz: 0.0,
} as const;

// ---- PolygonFilter（多角形柱）----
export const POLYGON_CONFIG = {
  polygon: [] as readonly [number, number][], // XY 頂点配列（Python 側デフォルト: 空）
  zMin: -20.0, // Z 下限 [m]
  zMax:  30.0, // Z 上限 [m]
} as const;

// ---- 現在アクティブなフィルター形状 ----
export type ActiveRangeFilter =
  | "frustum"
  | "cylindrical"
  | "box"
  | "spherical"
  | "polygon";
export const ACTIVE_FILTER: ActiveRangeFilter = "frustum";
