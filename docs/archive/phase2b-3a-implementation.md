# Phase 2b / 3a 実装記録 — 座標変換レイヤー・グローバルボクセル・Geo-Viewer

**実施日:** 2026-03-06 〜 2026-03-07
**担当:** Claude Sonnet 4.6 (Claude Code)
**ロードマップ参照:** `docs/implementation-roadmap.md`
**引き継ぎ先:** GitHub Copilot / 次期実装担当者

---

## 実装完了一覧

| Phase | 内容 | 状態 |
|-------|------|------|
| 2b-Step1 | `apps_ts/sensors.example.json` に `mount` ブロック追加 | 完了 |
| 2b-Step2-4 | `spatial-grid/` パッケージ（座標変換・型定義・空間IDコンバーター）| 完了 |
| 2b-Step5b | `geo-viewer/` パッケージ（CesiumJS + webpack）| 完了 |
| 2b-Step5c | `start.sh` 更新（geo-viewer 起動・config.json 自動生成）| 完了 |
| 3a | `viewer/` グローバルボクセルモード実装（GlobalVoxelLayer + GlobalVoxelRenderer）| 完了 |
| 3a | `viewer/src/main.ts` リライト（config.json 読み込み・モード切り替え）| 完了 |
| 3a | `viewer/webpack.config.js` 更新（`experiments.topLevelAwait: true`）| 完了 |
| 3a | `start.sh` 更新（viewer/config.json 自動生成）| 完了 |
| 3a+ | viewer 左右分割表示モード（`voxel_mode: "both"`）| 完了 |
| 3a+ | `start.sh` に `--split-view` / `--restart` オプション追加 | 完了 |

---

## アーキテクチャ概要

```
PCAP ──▶ Python パーサー ──▶ WebSocket ws://0.0.0.0:8765
                                 │
                    ┌────────────┼────────────────────┐
                    ▼            ▼                    ▼
             Detector        Viewer                Geo-Viewer
           (headless)      Port 3000              Port 3001
                         Three.js               CesiumJS
                      local / global       Google 3D Tileset
                        voxel mode          + point cloud
```

### モード選択

`viewer/` は `config.json` の `voxel_mode` で動作が変わる：

| `voxel_mode` | 説明 | 起動方法 |
|---|---|---|
| `"local"` (デフォルト) | センサーローカル XYZ 座標で表示 | `./start.sh` |
| `"global"` | WGS84 → センサーローカル逆変換で表示 | `viewer/config.json` を手動編集 |
| `"both"` | 左右分割表示（左: local / 右: global）| `./start.sh --split-view` |

**左右分割モード（`"both"`）の仕組み:**
- `body.split-mode` CSS クラスで `#viewer-split` を `display:flex` に切り替え
- `#viewer-left` / `#viewer-right` に別々の `ViewerApp` インスタンスを生成
- 1本の WebSocket から両 `FrameDispatcher` に同時ディスパッチ
- 各ペインに独立した `LayerPanel` UI

---

## 新規ファイル一覧

### `spatial-grid/` パッケージ

```
spatial-grid/
├── package.json         ESM, ts-jest
├── tsconfig.json        NodeNext, composite
├── jest.config.js       extensionsToTreatAsEsm: [".ts"]
├── src/
│   ├── types.ts         MountPosition / MountOrientation / SensorMount / DEFAULT_MOUNT
│   ├── euler-quaternion.ts  ZYX Euler → Quaternion → 回転行列
│   ├── coordinate-transform.ts  CoordinateTransformer クラス (変換/逆変換)
│   ├── spatial-id-converter.ts  ALoGS ラッパー (Node.js 専用)
│   └── index.ts         re-export
└── tests/
    ├── types.test.ts              3 tests
    ├── euler-quaternion.test.ts   12 tests
    └── coordinate-transform.test.ts  13 tests
```

**ブラウザ互換性:**
- `coordinate-transform.ts`, `euler-quaternion.ts` → Node.js API 不使用 → webpack バンドル可
- `spatial-id-converter.ts` → `createRequire` 使用 → **Node.js 専用**（ブラウザ不可）

### `geo-viewer/` パッケージ

```
geo-viewer/
├── package.json         cesium ^1.119, webpack, ts-loader, dotenv-webpack
├── tsconfig.json        NodeNext, lib: ES2022+DOM
├── tsconfig.webpack.json  ESNext + bundler 解決
├── webpack.config.js    CopyWebpackPlugin (Workers/Assets/Widgets), dotenv
├── .env.example         CESIUM_ION_TOKEN / GOOGLE_MAPS_API_KEY
├── index.html           cesiumContainer + info panel
├── src/
│   ├── types.ts         GeoViewerConfig
│   ├── point-cloud-layer.ts  PointPrimitiveCollection 管理
│   └── main.ts          top-level await fetch config.json + CesiumJS 初期化
└── config.json          ← start.sh が自動生成 (gitignore 推奨)
```

### `viewer/` 追加ファイル（Phase 3a）

```
viewer/src/
├── layers/
│   └── global-voxel-layer.ts   ← 新規: ALoGS Encode でボクセルキー生成
└── renderers/
    └── global-voxel-renderer.ts ← 新規: ALoGS Decode + inverseTransformPoint → InstancedMesh
```

---

## 座標変換パイプライン詳細

### 正変換: センサーローカル → WGS84

```
P_sensor (x, y, z)
  │
  │ Step 1: R_sensor (ZYX Euler → Quaternion → 回転行列)
  │         Rz(90° - heading) × Ry(-pitch) × Rx(roll)
  ▼
P_enu (East, North, Up)
  │
  │ Step 2: R_enu2ecef (ENU→ECEF 回転行列)
  │         列 = ENU 基底ベクトルの ECEF 表現
  ▼
dECEF (ECEF 変位)
  │
  │ Step 3: ECEF_origin (マウント位置の ECEF 座標) に加算
  ▼
ECEF_point
  │
  │ Step 4: Heikkinen 反復法 (5回)
  ▼
WGS84 (lat, lng, alt)
```

### 逆変換: WGS84 → センサーローカル

```
WGS84 (lat, lng, alt)
  → ECEF → dECEF (origin 引き算)
  → P_enu (R_enu2ecef の転置)
  → P_sensor (R_sensor の転置)
```

### 重要: ENU→ECEF 行列の定義（過去バグ修正済み）

ロードマップの行列定義が誤っていた（行と列が転置）。正しい実装：

```typescript
// 列 = ENU 基底ベクトルの ECEF 表現
return [
  [-sinL,          -sinP * cosL,   cosP * cosL ],  // 行 = ECEF x 成分
  [ cosL,          -sinP * sinL,   cosP * sinL ],  // 行 = ECEF y 成分
  [ 0,              cosP,          sinP        ],  // 行 = ECEF z 成分
];
// dECEF = R × [E, N, U]^T  ← これが正しい
```

誤りだったのは `dECEF = R^T × [E, N, U]^T` になる行列（ECEF→ENU 方向）をそのまま使っていた点。

---

## グローバルボクセル処理フロー（Three.js）

```
各フレームの点群 (PointData[])
  │
  │ GlobalVoxelLayer._buildSnapshot()
  │   p.z を -p.z に反転 (センサー下向き Z → Three.js 上向き Z)
  │   CoordinateTransformer.transformPoint(x, y, -z) → WGS84
  │   Encode.LatLngTo3DID(lat, lng, alt, unitM) → ALoGS キー
  ▼
VoxelSnapshot (Map<string, {count, lastUpdated}>)
  │
  │ GlobalVoxelRenderer.update()
  │   Decode.gridIdTo3DLocation(key) → WGS84 グリッド境界
  │   グリッド中心 (lat, lng, alt)
  │   CoordinateTransformer.inverseTransformPoint(lat, lng, alt) → sensor XYZ
  │   position.set(local.x, local.y, -local.z)  ← Z 反転 (Three.js 規約)
  │   scale.setScalar(unitM)
  ▼
THREE.InstancedMesh (最大 50,000 インスタンス)
  密度に応じた HSL カラー (青=疎 → 赤=密)
```

---

## config.json スキーマ

### `viewer/config.json`（`start.sh` が自動生成）

```json
{
  "websocket_url": "ws://127.0.0.1:8765",
  "voxel_mode": "local",
  "voxel_cell_size": 1.0,
  "global_voxel_unit_m": 10.0,
  "mount": {
    "position": { "lat": 34.649394, "lng": 135.001478, "alt": 54.0 },
    "orientation": { "heading": 0.0, "pitch": 0.0, "roll": 0.0 },
    "mounting_type": "pole_mounted"
  }
}
```

`global_voxel_unit_m` は `global` モード時のボクセルサイズ（m）。省略時デフォルト 10.0。

### `geo-viewer/config.json`（`start.sh` が自動生成）

```json
{
  "websocket_url": "ws://127.0.0.1:8765",
  "mount": {
    "position": { "lat": 34.649394, "lng": 135.001478, "alt": 54.0 },
    "orientation": { "heading": 0.0, "pitch": 0.0, "roll": 0.0 }
  }
}
```

---

## ALoGS ベンダーライブラリの注意事項

`vendor/alogs/` は CJS (TypeScript からトランスパイル済み)。

### TypeScript との interop

`Encode.d.ts` / `Decode.d.ts` は `export default class` を使っているが、NodeNext モジュール解決では CJS モジュールの static メソッドを正しく型推論できない。回避策：

```typescript
// viewer/src/layers/global-voxel-layer.ts
import Encode from "../../../vendor/alogs/Encode.js";
const key = (Encode as any).LatLngTo3DID(lat, lng, alt, this._unitM);

// viewer/src/renderers/global-voxel-renderer.ts
import Decode from "../../../vendor/alogs/Decode.js";
const bounds = (Decode as any).gridIdTo3DLocation(key) as { ... } | null;
```

webpack バンドル時は `__esModule: true` + `exports.default = Encode` を検出して正しく動作する（ランタイム問題なし）。`tsc --noEmit` でのみ `as any` キャストが必要。

### webpack ビルド警告（無害）

```
WARNING: export 'default' (imported as 'Encode') was not found in
  '../../../vendor/alogs/Encode.js' (module has no exports)
```

静的エクスポート解析の限界による警告で、ランタイム動作には影響しない。

---

## start.sh の動作フロー

```
Step 0: 前提条件チェック (python3, node, npm)
Step 1: cepf_sdk pip install
Step 2: ws-client / voxel / detector npm install + build
Step 2b: spatial-grid npm install + build
Step 3: viewer npm install + webpack bundle
Step 3b: geo-viewer npm install + webpack bundle (CesiumJS: 初回は長い)
Step 4: apps_ts npm install
Step 5: PCAP リプレイ起動 (WebSocket :8765)
Step 6: viewer/config.json 生成 → http-server :3000
Step 6b: geo-viewer/config.json 生成 → http-server :3001
Step 7: Detector 起動 (headless)
```

オプション：
- `--no-viewer` : Step 3 / Step 6 をスキップ
- `--no-geo-viewer` : Step 3b / Step 6b をスキップ
- `--no-detector` : Step 4 / Step 7 をスキップ
- `--split-view` : viewer を左右分割モード (`voxel_mode: "both"`) で起動
- `--install-only` : Step 5 以降をスキップ（インストールのみ）
- `--restart` : `.pids/` に記録された既存プロセスを kill してからクリーン起動

---

## テスト状況

```bash
# spatial-grid Jest テスト
cd spatial-grid && npm test
# 28 tests passed (types: 3, euler-quaternion: 12, coordinate-transform: 13)

# viewer TypeScript 型チェック
cd viewer && npx tsc --noEmit
# 0 errors

# viewer webpack ビルド
cd viewer && npm run bundle
# compiled with 2 warnings (ALoGS static analysis, 無害), 0 errors
# 出力: viewer/dist/bundle.js (1.8 MB)
```

---

## 既知の技術的負債

| 項目 | 詳細 | 優先度 |
|------|------|--------|
| `spatial-id-converter.ts` の型 | `createRequire` で ALoGS をロードするため型推論が弱い | 低 |
| ALoGS `as any` キャスト | NodeNext ↔ CJS `.d.ts` 非互換の回避策 | 低 |
| `geo-viewer/` テストなし | CesiumJS の Jest テストは困難（ブラウザ API 依存） | 中 |
| `GlobalVoxelRenderer` のパフォーマンス | 毎フレーム全キーをデコード・逆変換 → 大量ボクセル時にボトルネック | 中 |
| `viewer/config.json` が gitignore されていない | 環境依存ファイルは gitignore 推奨 | 低 |

---

## 次フェーズの実装候補（Phase 3b 以降）

ロードマップ `docs/implementation-roadmap.md` 参照。

主な未実装項目：
- **Phase 3b**: Detector のグローバルボクセルモード対応（`apps_ts/main-detector.ts` 更新）
- **Phase 4**: Geo-Viewer への WGS84 ヒートマップ表示（`geo-viewer/src/heatmap-layer.ts`）
- **Phase 5**: センサー設置座標の動的更新（GPS センサー連携）
- **Phase 6**: マルチセンサー統合（複数 CoordinateTransformer の管理）

---

## ファイル変更一覧（このフェーズの全変更）

### 新規作成

```
spatial-grid/package.json
spatial-grid/tsconfig.json
spatial-grid/jest.config.js
spatial-grid/src/types.ts
spatial-grid/src/euler-quaternion.ts
spatial-grid/src/coordinate-transform.ts
spatial-grid/src/spatial-id-converter.ts
spatial-grid/src/index.ts
spatial-grid/tests/types.test.ts
spatial-grid/tests/euler-quaternion.test.ts
spatial-grid/tests/coordinate-transform.test.ts
geo-viewer/package.json
geo-viewer/tsconfig.json
geo-viewer/tsconfig.webpack.json
geo-viewer/webpack.config.js
geo-viewer/.env.example
geo-viewer/index.html
geo-viewer/src/types.ts
geo-viewer/src/point-cloud-layer.ts
geo-viewer/src/main.ts
viewer/src/layers/global-voxel-layer.ts
viewer/src/renderers/global-voxel-renderer.ts
```

### 変更（既存ファイル）

```
apps_ts/sensors.example.json          → mount ブロック追加
viewer/index.html                      → #viewer-split / .viewer-pane 追加（分割レイアウト）
viewer/styles/style.css               → split-mode / .viewer-pane / .pane-label CSS 追加
viewer/src/main.ts                     → 全リライト（config.json 対応・"both"モード対応）
viewer/src/layers/index.ts             → GlobalVoxelLayer export 追加
viewer/webpack.config.js               → experiments.topLevelAwait: true 追加
viewer/tsconfig.webpack.json           → module: ESNext, target: ES2022 に変更
start.sh                               → Step 2b/3b/6b 追加、--split-view / --restart オプション追加
```
