# SASS（Sensor Analytics & Surveillance System）実装ロードマップ

**作成日:** 2026-03-06  
**最終更新:** 2026-03-07  
**ステータス:** Phase 1 完了、Phase 2a 開始準備中  
**注記:** viewer-dual-todo.md の内容を本ドキュメントに統合済み。深層レビュー指摘事項（22件）を反映済み。

---

## 目次

1. [現状分析](#現状分析)
2. [全体アーキテクチャ](#全体アーキテクチャ)
3. [Phase 別実装計画](#phase-別実装計画)
4. [両ビジュアライザ動作確認 実装手順](#両ビジュアライザ動作確認-実装手順python-変更なし方針)
5. [リスク管理](#リスク管理)
6. [時間見積もり](#時間見積もり)
7. [テスト戦略](#テスト戦略)
8. [深層レビュー：発見された問題点と必須修正事項](#深層レビュー発見された問題点と必須修正事項)

---

## 現状分析

### Phase 1 — 完了 ✓

```
実装済みコンポーネント：
├── voxel/              ローカルグリッド（高速、リアルタイム）
├── detector/           侵入検知エンジン（voxel依存）
├── viewer/             Three.js ローカル座標ビューワー
├── ws-client/          WebSocket クライアント
├── apps_ts/            Node.js ランタイム
├── cepf_sdk/           Python SDK (PCAP パーサー、フレーム処理)
├── start.sh            統合起動スクリプト
└── apps/               PCAP リプレイ (Python)
```

**稼働状況:**
- ✅ PCAP リプレイ → WebSocket (8765)
- ✅ Detector ← WebSocket (侵入検知実行中)
- ✅ Viewer ← WebSocket (Three.js ローカル座標表示)
- ✅ ローカルグリッド（voxel/）で毎フレーム ~65k 点処理可能

**制限事項:**
- ❌ グローバル座標（WGS84）への変換なし
- ❌ Google Maps / Cesium 統合なし
- ❌ センサー設置座標（GPS）管理なし
- ❌ 座標系キャリブレーション機構なし

---

## 全体アーキテクチャ

### 設計原則（前提条件）

1. **ローカルグリッドとグローバルグリッドは同時に使用しない** — 検知パイプラインのグリッド層は運用時にどちらか一方を選択する（config の `voxel_mode`）
2. **侵入検知の原理は座標系に依存しない** — 「背景を学習し、新規出現を侵入と判定する」アルゴリズムは、ボクセルキーが何であれ同一
3. **差し替えるのはグリッド層のみ** — 検知パイプライン (`BackgroundVoxelMap` → `computeDiff` → `IntrusionDetector`) は共有
4. **ビジュアライザはグリッドモードと連動する**
   - **ローカルモード**: viewer/ は `VoxelLayer` → `VoxelGrid`(`Math.floor`) でボクセルをセンサーローカル座標系に描画
   - **グローバルモード**: viewer/ は `GlobalVoxelLayer`（★新設） → `GlobalVoxelGrid`(ALoGS) でグローバルボクセルを構築し、各セル中心を `WGS84 → センサーローカル XYZ` に逆変換して Three.js に描画
   - **Cesium (geo-viewer/)** はグローバルモードに追加。同じ XYZ を WGS84 に変換して地球儀上に表示
   - グローバルモードでは Three.js と Cesium が**同時動作**可能（同じ WebSocket フィードを受信）
   - viewer/ のグリッド（表示用）と main-detector.ts のグリッド（検知用）は**別インスタンス**として並列動作

### 侵入検知の原理（座標系非依存）

```
【この原理はローカルでもグローバルでも完全に同一】

① 点群を受信
     ↓
② グリッドに投入 → VoxelSnapshot (Map<VoxelKey, VoxelState>)
     ↓                ↑
     │          キー生成だけが異なる
     │          ローカル: "ix:iy:iz" (Math.floor)
     │          グローバル: "A-12-34/567" (ALoGS 空間ID)
     ↓
③ 背景学習 (BackgroundVoxelMap.learn)
     ↓
④ 差分計算 (computeDiff)
     ↓
⑤ 閾値判定 (IntrusionDetector.evaluate)
     ↓
⑥ IntrusionEvent[] を出力
```

### 既存コードの検証結果

| コンポーネント | 所在 | 座標系依存性 | 結論 |
|---|---|---|---|
| `VoxelKey` = `string` | voxel/src/types.ts | **なし** | ローカルでもグローバルでも同じ型 |
| `VoxelState` | voxel/src/types.ts | **なし** | `{count, lastUpdated}` のみ |
| `VoxelSnapshot` | voxel/src/types.ts | **なし** | `Map<string, VoxelState>` |
| `BackgroundVoxelMap` | voxel/src/background-voxel-map.ts | **なし** | キー文字列だけで動作 |
| `computeDiff` | voxel/src/voxel-diff.ts | **なし** | `VoxelSnapshot` を受け取るだけ |
| `IntrusionDetector` | detector/src/intrusion-detector.ts | **なし** | `VoxelDiffEntry[]` を受け取るだけ。⚠️ P11: 現在 `bgStddev=0` が常に渡される問題あり |
| `VoxelGrid.addPoint()` | voxel/src/voxel-grid.ts | **ローカル専用** | `Math.floor(x/cellSize)` でキー生成 |

**結論:** 検知パイプラインの全段は既にジェネリック。ローカル専用なのは `VoxelGrid` のキー生成ロジック1箇所のみ。

### パッケージ構成（修正版）

```
[共有型定義 + 検知アルゴリズム]

  voxel/                      ← 共有型 + ローカルグリッド
  ├── types.ts                  VoxelKey, VoxelState, VoxelSnapshot, etc.
  │                             (座標系非依存 — ローカルでもグローバルでも使う)
  ├── background-voxel-map.ts   背景学習（座標系非依存）
  ├── voxel-diff.ts             差分計算（座標系非依存）
  └── voxel-grid.ts             ★ ローカル専用キー生成 "ix:iy:iz"

  detector/                   ← 侵入検知ロジック（座標系非依存）
  ├── intrusion-detector.ts     閾値判定（VoxelDiffEntry[] を受け取るだけ）
  └── threshold/                閾値戦略 (static, adaptive-mean, adaptive-stddev)


[ローカルモード]

  voxel/voxel-grid.ts
    XYZ → Math.floor → "ix:iy:iz"
    → VoxelSnapshot
    → BackgroundVoxelMap → computeDiff → IntrusionDetector

  ビジュアライザ:
    viewer/ (Three.js) — センサーローカル座標系
      ・点群          (PointCloudLayer)
      ・ボクセル       (VoxelLayer → VoxelGrid → InstancedMesh)
      ・range ワイヤー  (RangeWireframeLayer)


[グローバルモード]

  spatial-grid/                 ← ★新設
  ├── coordinate-transform.ts     XYZ → WGS84 変換 / WGS84 → センサーローカル XYZ 逆変換
  └── global-voxel-grid.ts        WGS84 → ALoGS 空間ID → VoxelSnapshot
      (voxel/types.ts の VoxelSnapshot を再利用)
    → VoxelSnapshot (同じ型!)
    → BackgroundVoxelMap → computeDiff → IntrusionDetector

  ビジュアライザ（同時動作可）:
    viewer/ (Three.js) — グローバルボクセルをセンサーローカル座標系で描画
      ・点群          (PointCloudLayer — ローカルモードと同一)
      ・ボクセル       (GlobalVoxelLayer★新設 → GlobalVoxelGrid(ALoGS)
                        → cellCenter(key): WGS84 → センサーローカル XYZ に逆変換
                        → InstancedMesh)
      ・range ワイヤー  (RangeWireframeLayer — ローカルモードと同一)
    geo-viewer/ (Cesium) — WGS84 座標系（XYZ→WGS84 変換後）
      ・点群 / ボクセル / range ワイヤー（地球儀上に表示）
```

### データフロー（修正版）

```
┌──────────────────────────────────────┐
│  PCAP リプレイ (Python)               │
│  → センサーローカル XYZ [m]           │
└──────────────┬───────────────────────┘
               │ WebSocket JSON @ 20Hz
               ▼
    ┌──────────────────────────┐
    │  WebSocket サーバー        │
    │  (ws://0.0.0.0:8765)     │
    └──────────┬───────────────┘
               │ （全クライアントが同じフィードを受信）
   ┌───────────┼─────────────────────────────────┐
   │           │                                 │
   ▼           ▼                                 ▼
┌──────────────────┐  ┌──────────────────────────────────────────────────┐
│viewer/           │  │   検知パイプライン (main-detector.ts)              │
│(Three.js)        │  │                                                  │
│port 3000         │  │  config の voxel_mode で排他的に選択              │
│                  │  │  ┌──────────────────┐  ┌─────────────────────┐  │
│[ローカルモード]  │  │  │ローカルモード     │  │グローバルモード       │  │
│VoxelLayer        │  │  │                  │  │                      │  │
│→VoxelGrid        │  │  │ VoxelGrid        │  │ CoordTransformer     │  │
│→InstancedMesh    │  │  │ Math.floor(x/sz) │  │ XYZ → WGS84         │  │
│                  │  │  │ "ix:iy:iz"       │  │  ↓                   │  │
│[グローバルモード]│  │  └────────┬─────────┘  │ GlobalVoxelGrid      │  │
│GlobalVoxelLayer★ │  │           │            │ ALoGS→空間ID          │  │
│→GlobalVoxelGrid  │  │           │            │ "A-12-34/567"         │  │
│→cellCenter逆変換 │  │           │            └──────────┬────────────┘  │
│→InstancedMesh    │  │           │                       │               │
└──────────────────┘  │           └──────────┬────────────┘               │
              │                      ▼                            │
              │  ┌───────────────────────────────────────────┐    │
              │  │  VoxelSnapshot (同じ型・同じ形式)           │    │
              │  │  Map<string, {count, lastUpdated}>         │    │
              │  └──────────────┬────────────────────────────┘    │
              │                 ▼ ← ここから先は完全に同一         │
              │  ┌──────────────────────────────┐                 │
              │  │ BackgroundVoxelMap.learn()    │ 背景学習        │
              │  │ computeDiff()                │ 差分計算        │
              │  │ IntrusionDetector.evaluate() │ 閾値判定        │
              │  └──────────────┬───────────────┘                 │
              │                 ▼                                  │
              │         IntrusionEvent[]                          │
              │         key / delta / timestamp                   │
              └──────────────────────────────────────────────────┘
                                 │
               ┌─────────────────┼──────────────────────┐
               ▼                 ▼                       ▼
        ┌────────────┐   ┌──────────────────┐    ┌──────────────┐
        │ console    │   │ イベント配信      │    │ (将来拡張)    │
        │ ログ出力   │   │ (WS port 8766★) │    │              │
        │ (両モード) │   └────────┬─────────┘    └──────────────┘
        └────────────┘            │
               ┌──────────────────┤
               ▼                  ▼
        ┌──────────────┐  ┌──────────────┐
        │ viewer/      │  │ geo-viewer/  │
        │ (Three.js)   │  │ (Cesium)     │
        │ 侵入ボクセル │  │ アラート     │
        │ を赤でハイ   │  │ オーバーレイ │
        │ ライト表示   │  │ (グローバル  │
        │ (ローカル    │  │  モード専用) │
        │  モード)     │  └──────────────┘
        └──────────────┘

  ★ port 8766 は仮。同一 WS チャネル(8765)の別メッセージ型でも可。Phase 3a で決定する。

【ビジュアライザとグリッドの対応】

  ローカルモード:
    センサーローカル XYZ
    ├── viewer/ (Three.js) — センサーローカル座標系
    │     ・点群          (PointCloudLayer)
    │     ・ボクセル       (VoxelLayer → VoxelGrid(Math.floor) → InstancedMesh)
    │     ・range ワイヤー  (RangeWireframeLayer)
    │     ・侵入ハイライト ← IntrusionEvent[] を WS 8766★ 経由で受信 → 該当ボクセルを赤表示
    └── main-detector.ts: VoxelGrid("ix:iy:iz") → 検知 → console + WS 8766★ でブロードキャスト
    ※ viewer/ の VoxelGrid（表示用）と detector の VoxelGrid（検知用）は別インスタンス

  グローバルモード（viewer/ と geo-viewer/ を同時起動）:
    センサーローカル XYZ
    ├── viewer/ (Three.js) — グローバルボクセルをセンサーローカル座標系に逆変換して描画
    │     ・点群          (PointCloudLayer — ローカルモードと同一)
    │     ・ボクセル       (GlobalVoxelLayer★ → GlobalVoxelGrid(ALoGS)
    │                       → cellCenter(key): WGS84 → センサーローカル XYZ
    │                       → InstancedMesh)
    │     ・range ワイヤー  (RangeWireframeLayer — ローカルモードと同一)
    │     ・侵入ハイライト ← IntrusionEvent[] を WS 8766★ 経由で受信 → 該当ボクセルを赤表示
    ├── geo-viewer/ (Cesium) — XYZ→WGS84 変換後、地球儀上で
    │     ・点群 / ボクセル / range ワイヤーフレーム
    │     ・侵入アラート  ← IntrusionEvent[] を WS 8766★ 経由で受信 → Cesium オーバーレイ
    └── main-detector.ts: GlobalVoxelGrid(ALoGS空間ID) → 検知 → console + WS 8766★ でブロードキャスト
    ※ viewer/ の GlobalVoxelGrid（表示用）と detector の GlobalVoxelGrid（検知用）は別インスタンス

  ※ Three.js のボクセル描画クラスはモードで切り替わる: VoxelLayer(ローカル) / GlobalVoxelLayer(グローバル)
  ※ Cesium はグローバルモード専用。同じ XYZ を WGS84 に変換して地球儀に重ねる
  ※ グローバルモードでは Three.js と Cesium が同じ WebSocket フィードを受信して並行動作
  ※ IntrusionEvent の配信経路（WS 8766 vs 8765 の別メッセージ型）は Phase 3a で決定する
```

### パッケージ依存グラフ（DAG）

```
[Python]
  cepf_sdk
    ↓ (フレーム配信)
  apps/pcap_replay.py
    ↓ WebSocket (8765、全クライアントにブロードキャスト)
    │
[Node.js/TypeScript]
    │
    ├──────────────────────────────────────────────────────
    │  【ビジュアライザ層】
    │  点群・ワイヤーフレームは座標系非依存。ボクセル描画のみグリッドモードと連動。
    ├──────────────────────────────────────────────────────
    │
    ├─→ viewer/                    (Three.js — 両モードで動作、ボクセル層はモード別)
    │   ├─→ ws-client/             WebSocket 8765 から XYZ (PointData[]) を受信
    │   ├─→ ws-client/             WebSocket 8766 から IntrusionEvent を受信 → 侵入ボクセル赤ハイライト
    │   │                          ⚠️ port 8766 は仮。8765 の別メッセージ型でも可。Phase 3a で決定。
    │   ├─→ voxel/voxel-grid.ts   [ローカルモード] VoxelLayer が VoxelGrid を内部保持
    │   ├─→ spatial-grid/coordinate-transform.ts  [グローバルモード] ブラウザ互換 — WGS84↔ローカルXYZ変換
    │   ├─→ spatial-grid/global-voxel-grid.ts      [グローバルモード] GlobalVoxelLayer が使用
    │   │     ⚠️ このファイルには createRequire を使わないブラウザ互換版が必要（後述 D-2 参照）
    │   └── ※ モードは viewer/config.json の voxel_mode で切り替え（D-3 参照）
    │
    ├─→ geo-viewer/ ★新設         (CesiumJS — グローバルモードで追加動作)
    │   ├─→ ws-client/             WebSocket 8765 から XYZ を受信
    │   ├─→ ws-client/             WebSocket 8766 から IntrusionEvent を受信 → Cesium アラート
    │   │                          ⚠️ port 8766 は仮。Phase 3a で決定。
    │   ├─→ spatial-grid/coordinate-transform.ts  ブラウザ互換（createRequire 不使用）
    │   ├─→ cesium                 WGS84 座標で地球儀表示
    │   └── ※ viewer/ と同時動作可能（同じ WebSocket フィードを共有）
    │        ⚠️ spatial-id-converter.ts / global-voxel-grid.ts は createRequire 使用のため不可
    │
    ├──────────────────────────────────────────────────────
    │  【検知パイプライン層 (main-detector.ts)】
    ├──────────────────────────────────────────────────────
    │
    ├─→ voxel/                    (共有型定義 + ローカルグリッド)
    │   ├── types.ts               ※ 全モードで使う共有型
    │   ├── background-voxel-map.ts ※ 全モードで使う共有アルゴリズム
    │   ├── voxel-diff.ts          ※ 全モードで使う共有アルゴリズム
    │   └── voxel-grid.ts          ★ ローカルモード専用グリッド
    │         Math.floor(x/cellSize) → "ix:iy:iz"
    │
    ├─→ spatial-grid/ ★新設       (グローバルグリッド + 座標変換)
    │   ├── coordinate-transform.ts  XYZ → WGS84（ブラウザ互換）
    │   ├── euler-quaternion.ts      Euler ↔ Quaternion（ブラウザ互換）
    │   ├── global-voxel-grid.ts   ★ グローバルモード専用グリッド
    │   │     WGS84 → ALoGS Encode → ALoGS空間ID
    │   ├── spatial-id-converter.ts  Node.js 専用（createRequire使用）
    │   └─→ voxel/types.ts         (VoxelSnapshot 型を再利用)
    │
    ├─→ vendor/                    (サードパーティ — リポジトリ直置き、CJS)
    │   ├── alogs/                  Encode.js / Decode.js
    │   ├── util/                   Util.js (alogs が内部で require)
    │   └── models/                 Model.d.ts (IGrid3D 型定義)
    │   ※ コピーせず現在位置のまま createRequire() で呼び出す
    │
    └─→ detector/                  (侵入検知 — 座標系非依存)
        ├─→ voxel/types.ts         (VoxelDiffEntry 型のみ)
        ├── threshold/
        └── ※ IntrusionEvent[] → console.log + WS 8766 ブロードキャスト
             → viewer/(ハイライト) / geo-viewer/(Cesiumアラート)
             ⚠️ WS 8766 は仮設計。8765 の別メッセージ型 or 専用ポートは Phase 3a で決定。
```

**グリッドモードと各コンポーネントの対応:**

| | ローカルモード | グローバルモード |
|---|---|---|
| グリッド（検知用） | `VoxelGrid` `"ix:iy:iz"` | `GlobalVoxelGrid` ALoGS空間ID |
| 座標変換 | なし | `CoordinateTransformer` XYZ↔WGS84 |
| 検知パイプライン | 共通 | 共通 |
| Three.js ボクセル層 | `VoxelLayer` → `VoxelGrid` | `GlobalVoxelLayer`★ → `GlobalVoxelGrid` → cellCenter逆変換 |
| Three.js 点群/ワイヤー | ✅ 共通（ローカル座標系） | ✅ 共通（ローカル座標系） |
| Three.js 侵入ハイライト | ⚠️ Phase 3a 実装予定（WS 8766 で受信・未実装）| ⚠️ Phase 3a 実装予定（WS 8766 で受信・未実装）|
| Cesium geo-viewer | ❌ 不要 | ✅ WGS84 座標（同時動作） |
| Cesium 侵入アラート | ❌ 不要 | ⚠️ Phase 3a 実装予定（WS 8766 で受信・未実装）|

**循環依存なし。** spatial-grid は voxel/types.ts のみに依存し、voxel-grid.ts には依存しない。

---

## Phase 別実装計画

### Phase 2: グローバル座標統合基盤構築

#### Phase 2a: センサーマウント情報管理 (1-2週間)

**目標:** センサー設置座標・姿勢パラメータを設定管理できるようにする

**実装内容:**

1. `apps_ts/sensors.example.json` 拡張

> **📌 正規の mount 座標値:** 以下の値は `apps/sensors.example.json` の `installation` ブロックに由来する。
> ドキュメント内の他の箇所でもこの値を使用すること（重複箇所: Phase 3a config, Step 1, P2 例）。

```json
{
  "websocket_url": "ws://127.0.0.1:8765",
  "voxel_cell_size": 1.0,
  "detector": { ... },
  "mount": {
    "position": {
      "lat": 34.649394,       // WGS84 緯度 [度]
      "lng": 135.001478,      // WGS84 経度 [度]
      "alt": 54.0             // WGS84 楕円体高 [m]（ジオイド高ではない）
    },
    "orientation": {
      "heading": 0.0,         // 方位角 [度] (0=真北)
      "pitch": 0.0,           // 仰角 [度] (0=水平)
      "roll": 0.0             // ロール [度] (0=水平)
    },
    "mounting_type": "pole_mounted"  // future: wall_mounted, etc.
  }
}
```

2. TypeScript 型定義 (`spatial-grid/src/types.ts`)

```typescript
export interface MountPosition {
  lat: number;      // WGS84 緯度 [度]
  lng: number;      // WGS84 経度 [度]
  alt: number;      // WGS84 楕円体高 [m]（ジオイド高ではない。日本では楕円体高 ≈ ジオイド高 + 約37m）
}

export interface MountOrientation {
  heading: number;  // Euler 角 [度]
  pitch: number;
  roll: number;
}

export interface SensorMount {
  position: MountPosition;
  orientation: MountOrientation;
  mounting_type: string;
}

export interface MeasurementError {
  position_m: number;       // GPS 計測誤差 3σ [m]
  orientation_deg: number;  // 角度キャリブレーション誤差 3σ [度]
  mounting_stability: "fixed" | "unstable";
}
```

3. Euler 角 ↔ Quaternion 変換ユーティリティ

```typescript
// spatial-grid/src/euler-quaternion.ts

export interface Quaternion {
  w: number;
  x: number;
  y: number;
  z: number;
}

export function eulerToQuaternion(
  heading_deg: number,
  pitch_deg: number,
  roll_deg: number
): Quaternion {
  // 航法規約：heading=0°=北、時計回り正
  // 内部で (90° - heading) を適用し、センサー x=前方 → ENU 北 へ変換
  // 参考: cepf_sdk/utils/quaternion.py
}

export function quaternionToEuler(q: Quaternion): {
  heading_deg: number;
  pitch_deg: number;
  roll_deg: number;
} {
  // 逆変換
}

/**
 * Quaternion → 3×3 回転行列
 * cepf_sdk/utils/quaternion.py の quaternion_to_rotation_matrix() の TS 版
 * 入力: {w, x, y, z}、出力: 3×3 number[][]
 */
export function quaternionToRotationMatrix(q: Quaternion): number[][] {
  const { w, x, y, z } = q;
  return [
    [1 - 2*(y*y + z*z),     2*(x*y - w*z),     2*(x*z + w*y)],
    [    2*(x*y + w*z), 1 - 2*(x*x + z*z),     2*(y*z - w*x)],
    [    2*(x*z - w*y),     2*(y*z + w*x), 1 - 2*(x*x + y*y)],
  ];
}
```

**ファイル構成:**

```
spatial-grid/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── types.ts                 ← SensorMount デフォルト値
│   ├── euler-quaternion.ts      ← 変換関数
│   └── (coordinate-transform.ts は Phase 2b で実装)
└── tests/
    ├── euler-quaternion.test.ts
    └── types.test.ts
```

**実装チェックリスト:**

- [ ] spatial-grid/ パッケージ初期化 (npm init, tsconfig.json)
- [ ] types.ts で SensorMount インターフェース定義
- [ ] euler-quaternion.ts で変換関数実装
- [ ] Jest テストケース（既知値での精度確認）
- [ ] sensors.example.json に mount ブロック追加
- [ ] start.sh で sensors.json を自動生成時に mount 情報をコピー
- [ ] ℹ️ 【Phase 3a で実施】`apps/sensors.example.json` の `installation` ブロックを apps_ts と同一定義に統一 (Py-4)
- [ ] ℹ️ 【Phase 3a で実施】config single-source 方針の決定（Phase 2a では案A: 二重管理許容）

**依存関係チェック:**

- ❌ voxel/ に変更なし（後方互換性維持）
- ❌ detector/ に変更なし
- ❌ viewer/ に変更なし
- ✅ spatial-grid/ は ws-client, voxel に依存しない（独立）

---

#### Phase 2b: 座標変換レイヤー実装 (2-3週間)

**目標:** センサーローカル XYZ → WGS84 勾配座標への物理的に正確な変換パイプライン
**副目標:** グローバルボクセル（空間ID）を生成し、detector・geo-viewer に供給

**座標変換の数学**

```
入力: 
  - センサーローカル座標  P_sensor = [x, y, z]ᵀ [m]
  - センサーマウント情報  (lat₀, lng₀, alt₀, heading, pitch, roll)

処理ステップ:

Step 1: センサーローカル → ENU (East-North-Up)

  座標系規約:
    センサーローカル: x = 前方、y = 左方、z = 上方
    ENU: x = East、y = North、z = Up
    heading: 方位角 [0° = 真北、時計回り正]
    pitch: 仰角 [0° = 水平、正 = 上向き]
    roll: ロール [0° = 水平、正 = 右傾き]

  heading=0 でセンサー x=前方 が ENU y=North に一致するよう変換:
    R_sensor = Rz(90° - heading) × Ry(-pitch) × Rx(roll)   [3×3]

  検証:
    heading=0:  R=Rz(90°) → [100,0,0] → [0,100,0] = 北に100m ✓
    heading=90: R=Rz(0°)  → [100,0,0] → [100,0,0] = 東に100m ✓

  P_enu = R_sensor × P_sensor                      [m, ENU フレーム]

Step 2: ENU → ECEF 回転行列（マウント位置で固定）
  φ = lat₀(rad), λ = lng₀(rad) とすると：
  R_enu2ecef = [
    [-sin(λ),         cos(λ),          0        ]
    [-sin(φ)cos(λ),  -sin(φ)sin(λ),    cos(φ)   ]
    [ cos(φ)cos(λ),   cos(φ)sin(λ),    sin(φ)   ]
  ]
  dECEF = R_enu2ecef × P_enu                       [m, ECEF 変位]

Step 3: ECEF 原点に加算
  ECEF₀ = LatLngAlt_to_ECEF(lat₀, lng₀, alt₀)    [m]
  ECEF  = ECEF₀ + dECEF                            [m]

Step 4: ECEF → WGS84 (緯度経度高度)
  (lat, lng, alt) = ECEF_to_LatLngAlt(ECEF)

出力:
  (lat, lng, alt) [度, 度, m]

※ R_enu2ecef はコンストラクタで一度だけ計算（全点で共有）
※ cepf_sdk/utils/coordinates.py に Python 版の lla_to_ecef/ecef_to_lla が既存
```

**実装:**

```typescript
// spatial-grid/src/coordinate-transform.ts

import { MountPosition, MountOrientation } from "./types.js";
import { eulerToQuaternion, quaternionToRotationMatrix } from "./euler-quaternion.js";

export class CoordinateTransformer {
  private readonly mount: { position: MountPosition; orientation: MountOrientation };
  private readonly R_sensor: number[][];     // センサーローカル→ENU 回転行列
  private readonly R_enu2ecef: number[][];   // ENU→ECEF 回転行列
  private readonly ECEF_origin: number[];    // ECEF原点キャッシュ

  constructor(mount: { position: MountPosition; orientation: MountOrientation }) {
    this.mount = mount;
    this.R_sensor = this.computeSensorRotation();
    this.R_enu2ecef = this.computeENUtoECEF();
    this.ECEF_origin = this.latLngAltToECEF(
      mount.position.lat,
      mount.position.lng,
      mount.position.alt
    );
  }

  /** センサーの Euler 角からセンサーローカル→ENU 回転行列を算出 */
  private computeSensorRotation(): number[][] {
    // 航法規約: heading=0°=北、時計回り正
    // センサー x=前方 が ENU y=North に一致するよう (90°-heading) を適用
    const q = eulerToQuaternion(
      this.mount.orientation.heading,
      this.mount.orientation.pitch,
      this.mount.orientation.roll
    );
    return quaternionToRotationMatrix(q);
  }

  /** マウント位置 (lat₀, lng₀) から固定の ENU→ECEF 回転行列を算出 */
  private computeENUtoECEF(): number[][] {
    const phi = (this.mount.position.lat * Math.PI) / 180;
    const lam = (this.mount.position.lng * Math.PI) / 180;
    const sinP = Math.sin(phi), cosP = Math.cos(phi);
    const sinL = Math.sin(lam), cosL = Math.cos(lam);
    return [
      [-sinL,        cosL,         0     ],
      [-sinP * cosL, -sinP * sinL, cosP  ],
      [ cosP * cosL,  cosP * sinL, sinP  ],
    ];
  }

  transformPoint(x: number, y: number, z: number): { lat: number; lng: number; alt: number } {
    // Step 1: センサーローカル → ENU
    const [e, n, u] = this.mat3x3MulVec(this.R_sensor, x, y, z);

    // Step 2: ENU → ECEF 変位 (回転行列で回す)
    const [dx, dy, dz] = this.mat3x3MulVec(this.R_enu2ecef, e, n, u);

    // Step 3: ECEF 原点に加算
    const ecef_x = this.ECEF_origin[0] + dx;
    const ecef_y = this.ECEF_origin[1] + dy;
    const ecef_z = this.ECEF_origin[2] + dz;

    // Step 4: ECEF → WGS84 緯度経度高度
    return this.ecefToLatLngAlt(ecef_x, ecef_y, ecef_z);
  }

  private mat3x3MulVec(R: number[][], x: number, y: number, z: number): [number, number, number] {
    return [
      R[0][0] * x + R[0][1] * y + R[0][2] * z,
      R[1][0] * x + R[1][1] * y + R[1][2] * z,
      R[2][0] * x + R[2][1] * y + R[2][2] * z,
    ];
  }

  private latLngAltToECEF(lat_deg: number, lng_deg: number, alt_m: number): number[] {
    // WGS84 パラメータ
    const a = 6378137.0;              // 長半径 [m]
    const f = 1 / 298.257223563;      // 扁平率
    const e2 = 2 * f - f * f;         // 離心率の二乗

    const lat_rad = (lat_deg * Math.PI) / 180;
    const lng_rad = (lng_deg * Math.PI) / 180;
    const N = a / Math.sqrt(1 - e2 * Math.sin(lat_rad) ** 2);

    const x = (N + alt_m) * Math.cos(lat_rad) * Math.cos(lng_rad);
    const y = (N + alt_m) * Math.cos(lat_rad) * Math.sin(lng_rad);
    const z = (N * (1 - e2) + alt_m) * Math.sin(lat_rad);

    return [x, y, z];
  }

  private ecefToLatLngAlt(x: number, y: number, z: number): { lat: number; lng: number; alt: number } {
    // WGS84 逆変換 (Heikkinen 反復法など)
    const a = 6378137.0;
    const f = 1 / 298.257223563;
    const e2 = 2 * f - f * f;

    const p = Math.sqrt(x * x + y * y);
    let lat_rad = Math.atan2(z, p * (1 - e2));

    // 数回の反復計算で収束
    for (let i = 0; i < 5; i++) {
      const N = a / Math.sqrt(1 - e2 * Math.sin(lat_rad) ** 2);
      lat_rad = Math.atan2(z + e2 * N * Math.sin(lat_rad), p);
    }

    const N = a / Math.sqrt(1 - e2 * Math.sin(lat_rad) ** 2);
    const cos_lat = Math.cos(lat_rad);
    // 極地付近での数値安定性ガード（Python 版 ecef_to_lla と同等）
    const alt = Math.abs(cos_lat) > 1e-10
      ? p / cos_lat - N
      : Math.abs(z) - N * (1 - e2);  // 極点付近の近似式
    const lng_rad = Math.atan2(y, x);

    return {
      lat: (lat_rad * 180) / Math.PI,
      lng: (lng_rad * 180) / Math.PI,
      alt: alt,
    };
  }
}

export function transformPointCloud(
  points: { x: number; y: number; z: number }[],
  mount: { position: MountPosition; orientation: MountOrientation }
): { lat: number; lng: number; alt: number }[] {
  const transformer = new CoordinateTransformer(mount);
  return points.map(p => transformer.transformPoint(p.x, p.y, p.z));
}
```

**空間ID ユーティリティ（spatial-id-converter.ts）:**

Phase 3a の `GlobalVoxelGrid` で利用するローレベルユーティリティ。
クラスではなく純粋関数として実装し、単一責務を維持する。

> **⚠️ Node.js 専用:** `createRequire` (Node.js API) を使用するため、**ブラウザバンドル不可**。
> geo-viewer（ブラウザアプリ）からはこのモジュールを import してはならない。
> geo-viewer で空間 ID の中心座標が必要な場合は、main-detector.ts から WebSocket 等で
> 変換済みデータを受信する設計とする。

```typescript
// spatial-grid/src/spatial-id-converter.ts
//
// ALoGS ライブラリの ESM ラッパー（ユーティリティ関数群）
// vendor/ に直置きされた CJS モジュールを createRequire() で呼び出す
// ※ vendor/alogs/ はコピーせず、リポジトリ内の現在位置をそのまま参照
// Phase 3a の GlobalVoxelGrid がこれらを使用する
// ⚠️ Node.js 専用 — ブラウザ (webpack) からは使用不可

import { createRequire } from "module";
const _require = createRequire(import.meta.url);

// vendor/alogs/*.js は CJS (require("../util/Util") 等の相対参照あり)
// createRequire で読み込めば Node.js が CJS として正しく解決する
const Encode = _require("../../vendor/alogs/Encode.js").default;
const Decode = _require("../../vendor/alogs/Decode.js").default;

// 型定義は vendor/models/Model.d.ts から
import type { IGrid3D } from "../../vendor/models/Model.js";

/**
 * WGS84 座標 → ALoGS 空間ID 文字列
 */
export function pointToSpatialId(
  lat: number, lng: number, alt: number, unit_m: number
): string {
  return Encode.LatLngTo3DID(lat, lng, alt, unit_m);
}

/**
 * ALoGS 空間ID → グリッド境界情報
 */
export function spatialIdToBounds(spatialId: string): IGrid3D {
  return Decode.gridIdTo3DLocation(spatialId);
}

/**
 * ALoGS 空間ID → グリッド中心座標
 */
export function spatialIdToCenter(spatialId: string): {
  lat: number; lng: number; alt: number
} {
  const bounds: IGrid3D = spatialIdToBounds(spatialId);
  return {
    lat: (bounds.bounds.north + bounds.bounds.south) / 2,
    lng: (bounds.bounds.east + bounds.bounds.west) / 2,
    alt: (bounds.altitude.upper + bounds.altitude.lower) / 2,
  };
}
```

**注:** `GlobalVoxelGrid` クラス（`VoxelGridLike` 実装）は Phase 3a で
`global-voxel-grid.ts` として実装する。ここではユーティリティ関数のみ。
```

**ファイル構成（Phase 2b 時点）:**

```
spatial-grid/src/
├── index.ts
├── types.ts                      (Phase 2a)
├── euler-quaternion.ts           (Phase 2a)
├── coordinate-transform.ts       ← NEW (Phase 2b)
└── spatial-id-converter.ts       ← NEW (Phase 2b) ユーティリティ関数
```

**注:** `global-voxel-grid.ts`（`VoxelGridLike` 実装クラス）と
`integration.ts`（パイプライン統合）は Phase 3a で追加する。
Phase 2b では座標変換と空間ID変換のユーティリティまでを実装し、
検知パイプラインとの接続は Phase 3a で行う。

**テスト:**

```typescript
// spatial-grid/tests/coordinate-transform.test.ts

describe("CoordinateTransformer", () => {
  test("既知点での精度確認", () => {
    // apps/sensors.example.json の installation と同一座標
    const mount = {
      position: { lat: 34.649394, lng: 135.001478, alt: 54.0 },
      orientation: { heading: 0, pitch: 0, roll: 0 },
    };

    const transformer = new CoordinateTransformer(mount);

    // センサー正前方 100m の点
    const result = transformer.transformPoint(100, 0, 0);

    // 期待値：北に 100m 進んだ座標（heading=0 = 北向き）
    expect(Math.abs(result.lat - 34.650293)).toBeLessThan(0.00001); // ±1.1m 以内
    expect(Math.abs(result.lng - 135.001478)).toBeLessThan(0.00001);
  });

  test("heading 90 度（東向き）", () => {
    const transformer = new CoordinateTransformer({
      position: { lat: 34.649394, lng: 135.001478, alt: 54.0 },
      orientation: { heading: 90, pitch: 0, roll: 0 },
    });

    const result = transformer.transformPoint(100, 0, 0);
    // センサーが東を向いているので、100m 進むと東方向
    expect(result.lng).toBeGreaterThan(135.001478);
  });
});
```

**実装チェックリスト:**

- [ ] coordinate-transform.ts 実装（ENU→ECEF 回転行列を含む正しい変換パイプライン）
- [ ] WGS84 ↔ ECEF 変換の精度確認（Heikkinen vs Vincenty）
- [ ] ENU→ECEF 回転行列の実装と単体テスト
- [ ] Euler 角回転の ZYX 順序確認
- [ ] Jest テストケース 10+ 点
- [ ] 性能テスト（1秒あたり 65k 点変換可能か）
- [ ] 数値安定性テスト（北極・南極での計算確認）
- [ ] start.sh で spatial-grid ビルド統合
- [ ] ℹ️ 【Phase 3a で実施】`websocket_server.py` に `installation` メッセージ送信追加 (Py-1, Py-2)
- [ ] ℹ️ 【Phase 3a で実施】`ouster_pcap_replay.py` を `CepfFrame` + `transport.send()` 経路に修正 (Py-3)
- [ ] ℹ️ 【Phase 3a で実施】`_frame_to_json()` に `installation` / `coordinate_system` フィールド追加 (Py-2)
- [ ] ℹ️ 【Phase 3a で実施】Python 側最小変更テスト（JSONスキーマ検証）

> **注:** Phase 2a・2b では Python 側は変更しない（案A: 二重管理で開始）。
> Python 側の変更 (Py-1～Py-5) は Phase 3a で実施し、案B（WebSocket 経由の自動同期）に移行する。

**精度要件:**

| パラメータ | 誤差予算 | 達成手段 |
|---|---|---|
| GPS 座標 | ±5 m (3σ) | RTK-GNSS 検討|
| heading | ±0.5° (3σ) | Phase 2c で検証 |
| pitch/roll | ±0.1° (3σ) | キャリブレーション |
| 最終的な点群XYZ誤差 | ±10 m @ 100m | 上記3項目の複合誤差 |

---

#### Phase 2c: キャリブレーション検証 & 自動調整 (2-3週間)

**目標:** 実地調査で heading/pitch/roll を精緻化し、座標変換精度を確保

**キャリブレーション方法:**

**方法1: Google Maps 視覚的照合（初期版）**

```bash
# geo-viewer がまだないので、Three.js viewer + Google Maps で目視比較
# 1. viewer/ で点群をローカル座標で表示
# 2. Google Maps 衛星写真で同じエリアを表示
# 3. 建物の輪郭が一致するまで heading を微調整
```

実装: キャリブレーション補助スクリプト

```typescript
// spatial-grid/tools/calibration-assistant.ts

export interface CalibrationResult {
  heading_correction_deg: number;
  pitch_correction_deg: number;
  roll_correction_deg: number;
  confidence_score: number;  // 0-1, 1 = 完全一致
}

export async function interactiveHeadingCalibration(
  mountConfig: SensorMount,
  pointCloud: { x: number; y: number; z: number }[]
): Promise<CalibrationResult> {
  // WebUI で heading を -180 〜 +180 度の範囲で調整
  // リアルタイムで点群を再変換して表示
  // ユーザーが「これで OK」と判定したら確定
}
```

**方法2: 既知点照合（自動化版）** (Phase 3a で実装)

```typescript
// Phase 3a で実装予定
// 地図上の既知点（建物角、マンホール蓋など）の座標を
// 手動または GIS データから取得して、
// 点群との照合誤差を最小化する heading/pitch/roll を
// 最小二乗法で自動計算
```

**ファイル構成:**

```
spatial-grid/
├── tools/
│   ├── calibration-assistant.ts  ← WebUI
│   └── calibration-validator.ts  ← 精度検証
└── docs/
    └── calibration-guide.md  ← マニュアル
```

**実装チェックリスト:**

- [ ] calibration-assistant.ts でコマンドラインツール作成
- [ ] Three.js viewer と Google Maps を並べるレイアウト案作成
- [ ] heading ±0.5° 精度での微調整UI実装
- [ ] キャリブレーション値の保存・復元機構
- [ ] 検証用の テストデータセット準備

---

### Phase 3: グローバルモード対応 & Cesium 地球儀ビューワー

#### Phase 3a: グローバルモード検知パイプライン構築 (3-4週間)

**目標:** spatial-grid/ の GlobalVoxelGrid を検知パイプラインに接続し、
グローバルボクセルで侵入検知を動作させる

**重要な前提:** detector/ は変更不要。既にジェネリックである。

**原理（グローバルモードでの侵入検知）:**

```
ローカルモード（Phase 1 完了済み）:
  XYZ → VoxelGrid.addPoint()     → VoxelSnapshot → 背景学習 → 差分 → 検知
               ↑                        ↑
        Math.floor(x/size)        "ix:iy:iz"

グローバルモード（Phase 3a で実装）:
  XYZ → CoordinateTransform      → VoxelSnapshot → 背景学習 → 差分 → 検知
        → GlobalVoxelGrid.addPoint()    ↑
               ↑                  "A-12-34/567"
        ALoGS Encode.LatLngTo3DID

※ → 以降のパイプライン (背景学習 → 差分 → 検知) は完全に同一
※ BackgroundVoxelMap, computeDiff, IntrusionDetector は変更なし
```

**GlobalVoxelGrid の実装:**

`GlobalVoxelGrid` は `VoxelGrid` と同じインターフェースを持つ。
唯一の違いは `addPoint()` でのキー生成方法。

```typescript
// spatial-grid/src/global-voxel-grid.ts

import type { VoxelKey, VoxelSnapshot, VoxelState } from "../../voxel/src/types.js";
import { CoordinateTransformer } from "./coordinate-transform.js";
import { SensorMount } from "./types.js";

// vendor/alogs は CJS（リポジトリ内 vendor/ に直置き）
// コピーせず createRequire() で現在位置のまま読み込む
import { createRequire } from "module";
const _require = createRequire(import.meta.url);
const Encode = _require("../../vendor/alogs/Encode.js").default;

export class GlobalVoxelGrid {
  private _cells = new Map<VoxelKey, VoxelState>();
  private _transformer: CoordinateTransformer;
  private _unit_m: number;

  constructor(mount: SensorMount, unit_m: number = 10.0) {
    this._transformer = new CoordinateTransformer(mount);
    this._unit_m = unit_m;
  }

  /**
   * センサーローカル XYZ を受け取り、グローバルボクセルに投入
   * VoxelGrid.addPoint() と同じシグネチャ
   */
  addPoint(x: number, y: number, z: number, frameId: number): void {
    // Step 1: ローカル XYZ → WGS84
    const { lat, lng, alt } = this._transformer.transformPoint(x, y, z);

    // Step 2: WGS84 → ALoGS 空間ID（これがグローバルボクセルのキー）
    const key: VoxelKey = Encode.LatLngTo3DID(lat, lng, alt, this._unit_m);

    // Step 3: VoxelState を更新（VoxelGrid と同じロジック）
    const existing = this._cells.get(key);
    if (existing) {
      existing.count += 1;
      existing.lastUpdated = frameId;
    } else {
      this._cells.set(key, { count: 1, lastUpdated: frameId });
    }
  }

  snapshot(): VoxelSnapshot {
    return new Map(this._cells);
  }

  clear(): void {
    this._cells.clear();
  }
}
```

**重要な点:**
- `GlobalVoxelGrid.addPoint()` と `VoxelGrid.addPoint()` は同じシグネチャ `(x, y, z, frameId)`
- 出力は同じ `VoxelSnapshot` 型
- 下流の `BackgroundVoxelMap`, `computeDiff`, `IntrusionDetector` は何も変える必要がない

**apps_ts/src/main-detector.ts（修正版）:**

```typescript
// apps_ts/src/main-detector.ts
// config の voxel_mode で "local" または "global" を切り替える

import { WsConnection } from "../../ws-client/src/ws-connection.js";
import { BackgroundVoxelMap } from "../../voxel/src/background-voxel-map.js";
import { computeDiff } from "../../voxel/src/voxel-diff.js";
import { IntrusionDetector } from "../../detector/src/intrusion-detector.js";
import { AdaptiveStddevThreshold } from "../../detector/src/threshold/adaptive-stddev.js";
import type { VoxelSnapshot } from "../../voxel/src/types.js";
import config from "../sensors.json";

// ── グリッド選択（排他的）──
interface VoxelGridLike {
  addPoint(x: number, y: number, z: number, frameId: number): void;
  snapshot(): VoxelSnapshot;
  clear(): void;
}

let grid: VoxelGridLike;

if (config.voxel_mode === "global") {
  // グローバルモード
  const { GlobalVoxelGrid } = await import("../../spatial-grid/src/global-voxel-grid.js");
  grid = new GlobalVoxelGrid(config.mount, config.global_voxel_unit_m ?? 10.0);
  console.log("[MODE] グローバルボクセル (ALoGS 空間ID)");
} else {
  // ローカルモード（デフォルト）
  const { VoxelGrid } = await import("../../voxel/src/voxel-grid.js");
  grid = new VoxelGrid(config.voxel_cell_size);
  console.log("[MODE] ローカルボクセル (センサー座標系)");
}

// ── 検知パイプライン（モードに関係なく同一）──
const bgMap = new BackgroundVoxelMap();
const strategy = new AdaptiveStddevThreshold(config.detector.sigma);
const detector = new IntrusionDetector(strategy);
const minSamples = config.detector.min_background_samples;

const conn = new WsConnection({
  url: config.websocket_url,
  reconnectInterval: 3000,
});

conn.connect();
let frameId = 0;

for await (const points of conn.frames()) {
  // ① グリッドに投入（ローカル or グローバル — config で決まる）
  grid.clear();
  for (const p of points) {
    grid.addPoint(p.x, p.y, p.z, frameId);
  }

  // ② スナップショット取得
  const snapshot = grid.snapshot();

  // ③ 背景学習
  bgMap.learn(snapshot);

  // ④ 背景が安定したら差分検知
  if (bgMap.isStable(minSamples)) {
    const diffs = computeDiff(snapshot, bgMap);
    const events = detector.evaluate(diffs);

    for (const event of events) {
      console.log(`[INTRUSION] key=${event.key}  delta=${event.delta.toFixed(1)}`);
    }
  }

  frameId++;
}
```

**sensors.json に追加するフィールド:**

```json
{
  "websocket_url": "ws://127.0.0.1:8765",
  "voxel_mode": "local",           // "local" or "global"（排他的選択）
  "voxel_cell_size": 1.0,          // ローカルモード用 [m]
  "global_voxel_unit_m": 10.0,     // グローバルモード用 [m]
  "detector": { ... },
  "mount": {                        // グローバルモード用
    "position": { "lat": 34.649394, "lng": 135.001478, "alt": 54.0 },
    "orientation": { "heading": 0.0, "pitch": 0.0, "roll": 0.0 },
    "mounting_type": "pole_mounted"
  }
}
```

**実装チェックリスト (Phase 3a):**

- [ ] `spatial-grid/src/global-voxel-grid.ts` 実装 (VoxelGridLike インターフェース準拠 + **ブラウザ互換版** — createRequire 不使用、vendor/alogs は webpack でバンドル次第）
- [ ] `VoxelGridLike` インターフェースを `voxel/src/types.ts` に追加（`addPoint`, `snapshot`, `clear`, `keyToCenter` を定義）
  - ✅ `VoxelGrid` の `keyToCenter(key)` は実コードに**既存実装済み**。インターフェース定義に含めればよい
  - `GlobalVoxelGrid` の `keyToCenter()` は ALoGS の `Decode.gridIdTo3DLocation()` → センター逆変換で実装
- [ ] `apps_ts/src/main-detector.ts` のモード切り替え実装
- [ ] `sensors.example.json` に `voxel_mode`, `mount`, `global_voxel_unit_m` 追加
- [ ] vendor/alogs CJS → ESM ラッパーの動作テスト
- [ ] vendor/alogs `.default` アクセスパターンの実行時検証 (P7)
- [ ] グローバルモードで BackgroundVoxelMap.learn() が正常動作するテスト
- [ ] グローバルモードで computeDiff() が正常動作するテスト
- [ ] グローバルモードで IntrusionDetector.evaluate() が正常動作するテスト（⚠️ E-2 修正後: stddev が適切に伝播すること）
- [ ] ローカルモードに一切影響がないことの回帰テスト
- [ ] 【Python: Phase 3a で実施】`_frame_to_json()` の `"type": "frame"` 追加 + `coordinate_system` フィールド出力テスト (Py-1, Py-2)
- [ ] 【Python: Phase 3a で実施】`WebSocketTransport` に config メッセージ送信機能追加 (Py-2)
- [ ] 【Python: Phase 3a で実施】`ouster_pcap_replay.py` に `--config` 引数追加 (Py-4)
- [ ] 【Python: Phase 3a で実施】WebSocket `installation` メッセージが Node.js 側で正しくパースされることの結合テスト
- [ ] `ws-client/src/ws-connection.ts` の `_parseMessage` で `type` フィールド対応（O-1 修正）
- [ ] `ws-client/src/types.ts` の `FrameMessage` に `type?: string` フィールド追加
- [ ] viewer/ の `fetch("/config.json")` 対応 — **D-3 実装:**
  - `start.sh` で `viewer/config.json` を自動生成（`voxel_mode`, `voxel_cell_size`, `websocket_url`）
  - `viewer/src/main.ts` 起動時に config fetch → `VOXEL_CELL_SIZE` ハードコードを廃止
  - `voxel_mode: "local" | "global"` に応じて `VoxelLayer` / `GlobalVoxelLayer` を選択
  - geo-viewer と同じパターン（`start.sh` が自動生成、`http-server` 経由で配信）

---

#### Phase 3b: Geo-viewer パッケージ作成 (3-4週間)

**目標:** CesiumJS で Google Maps 背景にWGS84 座標の点群・ボクセルを描画

**必要な前提条件:**

1. Google Cloud 認証キー取得
   - Project > API & Services > Credentials
   - API Key を作成（Maps SDK for JavaScript）
   - 無料枠: 月100万リクエスト

2. Cesium Ion Token 取得
   - cesium.com でアカウント作成
   - 無料で ImageryProvider と 3D Tiles にアクセス可能

**設計方針:**

> **重要:** geo-viewer は**表示専用**。侵入検知パイプラインは `main-detector.ts` に集約する。
> geo-viewer 内に検知ロジックを重複させると以下の問題が生じる：
> 1. `main-detector.ts` と検知結果が不一致になる可能性
> 2. `GlobalVoxelGrid` / `spatial-id-converter.ts` は `createRequire` (Node.js API) を使用しておりブラウザ非互換
> 3. ロジック変更時に2箇所の同期が必要
>
> 将来的に geo-viewer で侵入アラートを表示する場合は、
> `main-detector.ts` から WebSocket / HTTP で検知結果を受信する設計とする。

**実装:**

```typescript
// geo-viewer/src/main.ts
//
// geo-viewer は可視化専用 — 検知パイプラインは main-detector.ts に任せる
// WebSocket から受信した点群をリアルタイムで CesiumJS 地球儀上に描画する
// 座標変換 (CoordinateTransformer) はブラウザ互換（Node.js API 不使用）

import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

// API Keys（webpack の DefinePlugin または dotenv-webpack で注入）
const GOOGLE_MAPS_API_KEY = process.env.GOOGLE_MAPS_API_KEY || "";
const CESIUM_ION_TOKEN = process.env.CESIUM_ION_TOKEN || "";

Cesium.Ion.defaultAccessToken = CESIUM_ION_TOKEN;

// ── CesiumJS Viewer 初期化 ──
// ※ Google Photorealistic 3D Tiles は Cesium.Cesium3DTileset.fromUrl() で追加
const viewer = new Cesium.Viewer("cesiumContainer", {
  baseLayerPicker: false,
  timeline: false,
  animation: false,
});

// Google Photorealistic 3D Tiles を追加（CesiumJS 1.104+）
// ※ GooglePhotorealistic3DTileProvider は存在しない。
//    正しくは Cesium3DTileset.fromUrl() または createGooglePhotorealistic3DTileset() を使用。
try {
  const tileset = await Cesium.createGooglePhotorealistic3DTileset();
  viewer.scene.primitives.add(tileset);
} catch (e) {
  console.warn("Google 3D Tiles 読み込み失敗 — terrain のみで続行:", e);
  // Jetson の GPU メモリ不足時のフォールバック
}

// ── 設定読み込み（HTTP フェッチ — start.sh が config.json を生成）──
// ※ 静的 import ではなく fetch を使用。理由:
//    - ブラウザアプリなので webpack ビルド時に JSON が固定されるのを避ける
//    - start.sh が動的に mount 情報を注入する
const configResp = await fetch("/config.json");
const config = await configResp.json() as {
  websocket_url: string;
  mount: {
    position: { lat: number; lng: number; alt: number };
    orientation: { heading: number; pitch: number; roll: number };
  };
};

const mount = config.mount;

viewer.camera.setView({
  destination: Cesium.Cartesian3.fromDegrees(mount.position.lng, mount.position.lat, 500),
  orientation: {
    heading: Cesium.Math.toRadians(0),
    pitch: Cesium.Math.toRadians(-45),
    roll: 0,
  },
});

// ── 座標変換（ブラウザ互換 — createRequire 不使用）──
import { CoordinateTransformer } from "../../spatial-grid/src/coordinate-transform.js";
// ※ coordinate-transform.ts と euler-quaternion.ts は Node.js API 不使用のためバンドル可能
// ※ spatial-id-converter.ts は createRequire 使用のためブラウザ非互換 — ここでは使わない

const transformer = new CoordinateTransformer(mount);

// ── WebSocket 接続 ──
import { WsConnection } from "../../ws-client/src/ws-connection.js";

const conn = new WsConnection({
  url: config.websocket_url,
  reconnectInterval: 3000,
});

const pointPrimitives = viewer.scene.primitives.add(
  new Cesium.PointPrimitiveCollection({ blendOption: Cesium.BlendOption.TRANSLUCENT })
);

conn.connect();

for await (const localPoints of conn.frames()) {
  // 点群を WGS84 座標で描画
  pointPrimitives.removeAll();
  for (const p of localPoints) {
    const wgs = transformer.transformPoint(p.x, p.y, p.z);
    pointPrimitives.add({
      position: Cesium.Cartesian3.fromDegrees(wgs.lng, wgs.lat, wgs.alt),
      pixelSize: 3,
      color: Cesium.Color.YELLOW,
    });
  }
}
```

**ポイント:**
- geo-viewer は**可視化専用** — 検知は `main-detector.ts` に集約（ロジック重複回避）
- `CoordinateTransformer` と `euler-quaternion.ts` は**ブラウザ互換**（Node.js API 不使用）
- `spatial-id-converter.ts` / `GlobalVoxelGrid` は `createRequire` を使うため**ブラウザ非互換** — geo-viewer では使わない
- config は `fetch("/config.json")` で動的取得（`start.sh` が生成）
- `Cesium.createGooglePhotorealistic3DTileset()` を使用（`GooglePhotorealistic3DTileProvider` は存在しない API）

**package.json:**

```json
{
  "name": "geo-viewer",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch",
    "serve": "npx http-server . -p 3001 --cors",
    "test": "jest"
  },
  "dependencies": {
    "cesium": "^1.119.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/node": "^20.0.0"
  }
}
```

**ファイル構成:**

```
geo-viewer/
├── package.json
├── tsconfig.json
├── index.html
├── .env.example        # CESIUM_ION_TOKEN=xxx, GOOGLE_MAPS_KEY=xxx
├── src/
│   ├── main.ts               # エントリーポイント（表示専用、検知ロジックなし）
│   ├── point-cloud-layer.ts  # PointPrimitive 管理
│   └── types.ts
├── dist/
│   └── (webpack bundle)
└── tests/
    ├── e2e.test.ts
    └── coordinate-transform.integration.test.ts
```

**実装チェックリスト:**

- [ ] geo-viewer/ パッケージ初期化
- [ ] `Cesium.createGooglePhotorealistic3DTileset()` での Google 3D Tiles 統合確認
- [ ] Jetson (ARM/Maxwell or Pascal GPU) での CesiumJS + WebGL 動作確認（X-2 参照）
- [ ] coordinate-transformer 連携テスト
- [ ] PointPrimitive 毎フレーム更新パフォーマンステスト
- [ ] 環境変数管理 (.env)
- [ ] config.json fetch による動的設定読み込みテスト
- [ ] ⚠️ geo-viewer には検知パイプラインを含めない（main-detector.ts に集約）

**ボクセル・ワイヤーフレームの Cesium 描画 — Phase 3b 設計メモ:**

> ⚠️ Phase 3b ではまず**点群表示だけ**実装する。ボクセル/ワイヤーフレームは要件確定後に追加。以下は実装時の設計案。

| 要素 | 実装方法 |
|---|---|
| 侵入ボクセル（赤表示） | `Cesium.BoxGeometry` プリミティブ × IntrusionEvent ボクセル数。`spatialIdToCenter(key)` → WGS84 → `Cesium.Cartesian3.fromDegrees()` |
| 背景ボクセルグリッド | 同上、透明度上げて淡表示 |
| range ワイヤーフレーム | `Cesium.PolylineCollection` — WGS84 境界座標の頂点を `CoordinateTransformer` で変換 |

> **実装済み制約:** `spatial-id-converter.ts` / `global-voxel-grid.ts` は `createRequire` でブラウザ非互換。
> geo-viewer 内で ALoGS キーをデコードするのは不可。代わりに `main-detector.ts` が
> WS 8766 経由で IntrusionEvent（キー娴 + WGS84 中心座標）を送信する設計を標準とする。

---

#### Phase 3c: インタラクティブUI & 設定パネル (2週間)

**目標:** ブラウザから heading/pitch/roll をリアルタイム調整、キャリブレーション検証

**機能:**

```typescript
// geo-viewer/src/calibration-panel.ts

export class CalibrationPanel {
  private mount: SensorMount;

  renderHeadingSlider(): void {
    const slider = document.getElementById("heading-slider") as HTMLInputElement;
    slider.addEventListener("input", (e) => {
      this.mount.orientation.heading = parseFloat(e.currentTarget.value);
      this.recomputePointCloud();
    });
  }

  renderPitchSlider(): void { /* similar */ }
  renderRollSlider(): void { /* similar */ }

  exportCalibrationJSON(): void {
    const json = JSON.stringify(this.mount, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sensor-mount-calibration.json";
    a.click();
  }
}
```

**HTML Layout:**

```html
<!DOCTYPE html>
<html>
<head>
  <title>SASS Geo-Viewer</title>
  <link rel="stylesheet" href="./styles/main.css" />
</head>
<body>
  <div id="main-container">
    <!-- Cesium Viewer -->
    <div id="cesiumContainer"></div>

    <!-- Calibration Panel (右側) -->
    <div id="calibration-panel" class="panel">
      <h3>キャリブレーション</h3>
      <div class="control-group">
        <label>Heading (°): <span id="heading-value">0.0</span></label>
        <input id="heading-slider" type="range" min="-180" max="180" step="0.1" value="0" />
      </div>
      <div class="control-group">
        <label>Pitch (°): <span id="pitch-value">0.0</span></label>
        <input id="pitch-slider" type="range" min="-90" max="90" step="0.1" value="0" />
      </div>
      <div class="control-group">
        <label>Roll (°): <span id="roll-value">0.0</span></label>
        <input id="roll-slider" type="range" min="-180" max="180" step="0.1" value="0" />
      </div>
      <button id="export-btn">設定をエクスポート</button>
      <button id="reset-btn">リセット</button>
    </div>

    <!-- Info Panel -->
    <div id="info-panel" class="panel">
      <h3>情報</h3>
      <div id="fps">FPS: --</div>
      <div id="point-count">Points: --</div>
    </div>
  </div>

  <script src="./dist/main.js"></script>
</body>
</html>
```

**実装チェックリスト:**

- [ ] HTML/CSS レイアウト
- [ ] heading/pitch/roll スライダー UI
- [ ] リアルタイム座標再計算・描画更新
- [ ] キャリブレーション値の localStorage 保存
- [ ] JSON エクスポート機能
- [ ] FPS/ポイント数表示

---

## 両ビジュアライザ動作確認 実装手順（Python 変更なし方針）

**方針:** Phase 2a〜2b では Python 側は一切変更しない（案A: 二重管理で開始）。Node.js 側のみで両ビジュアライザを動作させる。  
Phase 3a で Python 側の最小変更 (Py-1〜Py-5) を実施し、案B（WebSocket 経由の自動同期）に移行する。  
Python 変更の詳細は [深層レビュー: Python 側の最小必須変更一覧](#python-側の最小必須変更一覧) を参照。  
Phase 2a〜3b の具体的な即時実装ガイド。

### 基本方針

```
┌─────────────────────────────┐
│  Phase 2a〜2b で変更しないもの │
│  ─────────────────────────  │
│  • Python コード全体         │
│  • WebSocket ペイロード形式  │
│    {frame_id, timestamp,     │
│     points:{x,y,z}}          │
│  • apps/sensors.example.json │
│  • cepf_sdk/*                │
│                              │
│  ※ Phase 3a で Py-1〜Py-5 の │
│    最小変更を実施する         │
└─────────────────────────────┘

┌──────────────────────────────────────┐
│  変更・新規作成するもの（Node.js）    │
│  ────────────────────                │
│  • apps_ts/sensors.example.json      │
│    → mount ブロック追加               │
│  • spatial-grid/ (新パッケージ)      │
│    → 座標変換 (XYZ→WGS84)           │
│  • geo-viewer/ (新パッケージ)        │
│    → CesiumJS 地球儀ビューワー       │
│  • start.sh                          │
│    → geo-viewer 起動ステップ追加     │
└──────────────────────────────────────┘
```

**データフロー:**

```
Python (変更なし)                    Node.js (変更あり)
─────────────────                    ──────────────────
PCAP → Parser → WS (port 8765)
         │
         ├──→ viewer/ (port 3000)       ← 既存 (変更なし)
         │     Three.js ローカル座標
         │
         └──→ geo-viewer/ (port 3001)   ← 新規
               CesiumJS 地球儀
               CoordinateTransformer で XYZ→WGS84 変換
               マウント情報は Node.js config から取得
```

**重要:** マウント情報 (lat, lng, alt, heading, pitch, roll) は Python の WebSocket には
含まれない。Node.js 側の `sensors.json` からのみ取得する。
Python 側への `installation` メッセージ追加は、後日 Python 担当者と協議する。

### 現状サマリー

| コンポーネント | 状態 | 備考 |
|---|---|---|
| Python PCAP → WS | ✅ 動作済み | port 8765, JSON |
| ws-client/ | ✅ 動作済み | ブラウザ / Node.js 両対応 |
| voxel/ | ✅ 動作済み | ローカルグリッド |
| detector/ | ✅ 動作済み | ヘッドレス検知 |
| viewer/ (Three.js) | ✅ 動作済み | port 3000 |
| spatial-grid/ | ❌ 未実装 | 座標変換 |
| geo-viewer/ (CesiumJS) | ❌ 未実装 | 地球儀ビューワー |

---

### Step 0: 環境復旧 & ローカルビューワー動作確認

**目的:** reboot 後の環境が正常であることを確認

- [ ] `./start.sh` を実行して全コンポーネント起動
- [ ] http://localhost:3000 でローカルビューワーに点群が表示されることを確認
- [ ] `tail -f .logs/detector.log` で侵入検知ログが流れることを確認
- [ ] `./start.sh --stop` で全プロセス停止

**所要時間:** 10 分

---

### Step 1: Node.js 設定ファイルにマウント情報を追加 → [Phase 2a 詳細](#phase-2a-センサーマウント情報管理-1-2週間)

**目的:** geo-viewer が必要とするセンサー設置位置情報を Node.js config に追加

#### 1-1. `apps_ts/sensors.example.json` にマウントブロックを追加

```json
{
  "websocket_url": "ws://192.168.1.100:8765",
  "voxel_cell_size": 1.0,
  "detector": {
    "strategy": "adaptive-stddev",
    "sigma": 2.0,
    "min_background_samples": 30
  },
  "mount": {
    "position": {
      "lat": 34.649394,
      "lng": 135.001478,
      "alt": 54.0
    },
    "orientation": {
      "heading": 0.0,
      "pitch": 0.0,
      "roll": 0.0
    },
    "mounting_type": "pole_mounted"
  }
}
```

> **値の出典:** `apps/sensors.example.json` の `installation` ブロック  
> reference_latitude → lat, reference_longitude → lng, reference_altitude → alt  
> orientation はデフォルト (0,0,0) — Phase 2c のキャリブレーション後に更新

> `start.sh` の sensors.json 自動生成は現状のコードで動作する（example をベースに websocket_url を localhost に置換）。**start.sh の修正は不要**。
> ⚠️ **注意:** `start.sh` は `apps_ts/sensors.json` が既に存在する場合は再生成しない。mount ブロック追加後は `rm apps_ts/sensors.json` を実行してから `./start.sh` すること。

#### 1-2. `main-detector.ts` の config 型を更新

```typescript
const config: {
  websocket_url: string;
  voxel_cell_size: number;
  detector: { strategy: string; sigma: number; min_background_samples: number };
  mount?: {
    position: { lat: number; lng: number; alt: number };
    orientation: { heading: number; pitch: number; roll: number };
  };
} = ...;
```

> mount は optional — ローカルモード（現状）では使わないため

#### チェックポイント

- [ ] `apps_ts/sensors.example.json` に mount ブロック追加済み
- [ ] `rm apps_ts/sensors.json && ./start.sh` → sensors.json に mount が含まれること確認
- [ ] detector が正常動作すること確認（mount 追加で壊れないこと）

**所要時間:** 30 分

---

### Step 2: spatial-grid パッケージ作成 → [Phase 2b 詳細](#phase-2b-座標変換レイヤー実装-2-3週間)

**目的:** センサーローカル XYZ → WGS84 (lat, lng, alt) への変換を提供

> **注:** この Step では vendor/alogs（空間ID変換）は使わない。  
> 空間 ID はグローバルボクセル検知で必要になるが、ビジュアライザには不要。

#### パッケージ構成

```
spatial-grid/
├── package.json
├── tsconfig.json
├── jest.config.js
├── src/
│   ├── index.ts
│   ├── types.ts                     # MountPosition, MountOrientation, SensorMount
│   ├── coordinate-transform.ts      # CoordinateTransformer (メインクラス)
│   └── euler-quaternion.ts          # Euler 角 → 回転行列
└── tests/
    ├── coordinate-transform.test.ts
    └── euler-quaternion.test.ts
```

#### テスト期待値

| テストケース | 期待値 |
|---|---|
| 原点 (0,0,0) → マウント位置自体 | lat≈34.6494, lng≈135.0015, alt≈54.0 |
| (100,0,0) heading=0 → 北に100m | lat がわずかに増加（センサー x=前方, heading=0=北） |
| (0,100,0) heading=0 → 西に100m | lng がわずかに減少（センサー y=左方 → ENU 西） |
| (0,0,10) → 上に10m | alt が 64.0 付近 |
| 往復精度: transform → inverse → 原点誤差 < 1mm | |

#### チェックポイント

- [ ] `cd spatial-grid && npm test` — 全テスト pass
- [ ] (0,0,0) → マウント位置への変換精度 < 0.001°
- [ ] 65,000 点の変換が 50ms 以内（性能テスト）
- [ ] ブラウザバンドル可能（`coordinate-transform.ts` と `euler-quaternion.ts` は Node.js API 不使用）
- [ ] ❗ `spatial-id-converter.ts` は `createRequire` 使用のため Node.js 専用。ブラウザからは使用不可。

**所要時間:** 3-4 日

---

### Step 3: geo-viewer パッケージ作成 → [Phase 3b 詳細](#phase-3b-geo-viewer-パッケージ作成-3-4週間)

**目的:** CesiumJS でリアルタイム点群を地球儀上に表示

#### 3-0. 事前準備: API キー取得

- [ ] **Cesium Ion Token** — https://cesium.com/ion/tokens
  - アカウント作成 → Access Token 発行（無料枠で十分）
- [ ] **Google Maps API Key** — https://console.cloud.google.com/
  - Map Tiles API を有効化 (Google Photorealistic 3D Tiles 用)
  - 無料枠: 月 100 万リクエスト
  - キーは `geo-viewer/.env` に保存し .gitignore に追加

#### パッケージ構成

```
geo-viewer/
├── .env.example              # CESIUM_ION_TOKEN=xxx, GOOGLE_MAPS_KEY=xxx
├── .gitignore                # .env, dist/, node_modules/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.webpack.json
├── webpack.config.js
├── src/
│   ├── main.ts               # エントリーポイント
│   ├── cesium-app.ts         # CesiumJS Viewer 初期化
│   └── geo-point-cloud.ts    # 点群描画レイヤー
└── styles/
    └── style.css
```

#### 依存関係

```json
{
  "dependencies": { "cesium": "^1.119.0" },
  "devDependencies": {
    "typescript": "^5.0.0",
    "webpack": "^5.0.0",
    "webpack-cli": "^5.0.0",
    "ts-loader": "^9.0.0",
    "copy-webpack-plugin": "^12.0.0",
    "dotenv-webpack": "^8.0.0"
  }
}
```

#### マウント設定のブラウザへの受け渡し（config.json を HTTP 配信）

```
start.sh が geo-viewer/config.json を生成:
  {
    "websocket_url": "ws://127.0.0.1:8765",
    "mount": { "position": {...}, "orientation": {...} }
  }

main.ts 起動時:
  const config = await fetch("/config.json").then(r => r.json());
  const transformer = new CoordinateTransformer(config.mount);
```

> geo-viewer/ ディレクトリ自体を http-server で配信するため、
> config.json をそこに置けばフェッチ可能。

#### 性能考慮

| 項目 | 対策 |
|---|---|
| 65k 点/フレーム × 20 Hz | PointPrimitiveCollection で GPU 描画 |
| GC 圧力 | `removeAll()` + 再追加 (Cesium はこれを最適化) |
| 座標変換コスト | CoordinateTransformer は行列をキャッシュ済み |
| 代替案 | 点が多すぎる場合は間引き or CustomPrimitive + GLSL |

> 初期目標: 20 Hz でストレスなく描画。もし重ければ 5 Hz にダウンサンプル。

#### チェックポイント

- [ ] `cd geo-viewer && npm run bundle` — ビルド成功
- [ ] `npx http-server . -p 3001` → http://localhost:3001 で CesiumJS の地球儀が表示
- [ ] Google 3D Tiles が読み込まれ、建物が表示される
- [ ] WebSocket 未接続でもクラッシュしない (再接続待ち状態)
- [ ] WebSocket 接続後、点群が明石市付近に表示される
- [ ] 点群がフレーム毎にリアルタイム更新される

**所要時間:** 5-7 日

---

### Step 4: start.sh 更新

**目的:** geo-viewer のビルド・配信・停止を start.sh に統合

#### 変更内容

1. **geo-viewer/config.json 自動生成**

```bash
python3 -c "
import json, pathlib
src = pathlib.Path('apps_ts/sensors.example.json').read_text()
obj = json.loads(src)
out = {
  'websocket_url': 'ws://127.0.0.1:$WS_PORT',
  'mount': obj.get('mount', {})
}
print(json.dumps(out, indent=2, ensure_ascii=False))
" > geo-viewer/config.json
```

2. **viewer/config.json 自動生成** (D-3 対応 — Phase 3a 実装時に追加)

```bash
python3 -c "
import json, pathlib
src = pathlib.Path('apps_ts/sensors.example.json').read_text()
obj = json.loads(src)
out = {
  'websocket_url': 'ws://127.0.0.1:$WS_PORT',
  'voxel_mode': obj.get('voxel_mode', 'local'),
  'voxel_cell_size': obj.get('voxel_cell_size', 1.0)
}
print(json.dumps(out, indent=2, ensure_ascii=False))
" > viewer/config.json
```

> viewer/ ディレクトリを `http-server` で配信するため、`viewer/config.json` が自動的に `fetch("/config.json")` で取得可能。
> 現在 `viewer/src/main.ts` は `VOXEL_CELL_SIZE=1.0` をハードコード— Phase 3a で fetch 機構に置き換える。

2. **geo-viewer ビルド** (`npm run bundle`)
3. **geo-viewer 配信** (`npx http-server . -p 3001 --cors`)
4. **`--no-geo-viewer` フラグ追加**
5. **完了サマリー更新**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SASS 起動完了!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WebSocket   ws://0.0.0.0:8765
  Viewer      http://localhost:3000   (Three.js ローカル座標)
  Geo-Viewer  http://localhost:3001   (CesiumJS 地球儀)
  Detector    ヘッドレス侵入検知
```

#### チェックポイント

- [ ] `./start.sh` で 4 つのコンポーネント起動 (PCAP + Viewer + Geo-Viewer + Detector)
- [ ] `./start.sh --no-geo-viewer` で geo-viewer なし起動
- [ ] `./start.sh --stop` で全プロセス停止（geo-viewer 含む）

**所要時間:** 1-2 時間

---

### Step 5: 両ビジュアライザ同時動作確認

**目的:** ゴール — 同一の WS フィードから両方のビューワーがリアルタイム表示

#### テスト手順

```
1. ./start.sh
2. ブラウザで 2 タブ開く:
   - Tab 1: http://localhost:3000  (ローカルビューワー)
   - Tab 2: http://localhost:3001  (geo-viewer)
```

| 確認項目 | Tab 1 (ローカル) | Tab 2 (geo-viewer) |
|---|---|---|
| 点群表示 | ✅ センサーローカル座標 | ✅ 地球儀上 (明石付近) |
| リアルタイム更新 | ✅ 20 Hz | ✅ 20 Hz (or 下限) |
| 接続状態 | "WS: 接続済み ✓" | "WS: 接続済み ✓" |
| レスポンス | 遅延なし | 遅延 < 200ms |
| カメラ操作 | OrbitControls | CesiumJS 地球儀操作 |

#### 完了条件

```
Two tabs side by side:
┌─────────────────────────┐  ┌─────────────────────────┐
│  Three.js (ローカル)     │  │  CesiumJS (地球儀)       │
│                         │  │                         │
│    [点群: XYZ 座標]      │  │  [点群: 明石市上空]      │
│                         │  │  [Google 3D 建物]        │
│  WS: 接続済み ✓          │  │  WS: 接続済み ✓          │
│  フレーム: 1234          │  │  フレーム: 1234          │
│  点数: 65432             │  │  点数: 65432             │
└─────────────────────────┘  └─────────────────────────┘
```

#### 追加確認

- [ ] WS 切断時にどちらもクラッシュせず再接続を試みること
- [ ] Python PCAP リプレイを再起動したら自動再接続されること
- [ ] 3 分間の連続動作でメモリリーク兆候がないこと (DevTools > Memory)

**所要時間:** 半日（バグフィックス込み）

---

### Step 6: (後日) Python 担当者との協議事項

両ビジュアライザ動作確認完了後、Python 担当者と以下を議論:

| # | テーマ | 目的 | Node.js での暫定対処 |
|---|---|---|---|
| 1 | **WebSocket ペイロード拡張** | `installation` メッセージをWS初回接続時に送信 | Node.js が sensors.json からマウント情報を取得（現在の方式） |
| 2 | **設定ファイル統一** | Python/Node.js で mount の single-source 化 | 両側で手動同期（sensors.example.json の mount 値を合わせる） |
| 3 | **ouster_pcap_replay.py 修正** | CepfFrame + transport.send() 経由にする | 現状のバイパスで動作はするので後回し |
| 4 | **_frame_to_json() 拡張** | type, coordinate_system フィールド追加 | Node.js 側でデフォルト "SENSOR_LOCAL" と仮定 |
| 5 | **タイムスタンプ整合** | time.time() vs PCAP タイムスタンプ | Node.js 側で無視（frame_id で管理） |

#### 議論のポイント

```
Q1: mount 情報の正規の置き場所は Python config? Node.js config? 共有 JSON?
    → 提案: apps/sensors.example.json の installation を正とし、
      Node.js は起動時にそこから読む (start.sh で変換コピー)

Q2: WebSocket で installation を送信するべきか?
    → 提案: 接続初回に {"type":"config","installation":{...}} を送信
      Node.js 側はこれを受信したら sensors.json の mount を上書き

Q3: ouster_pcap_replay.py の CepfFrame 回帰は必須か?
    → 現状バイパスでも動作上問題なし。
      ただしフィルタパイプラインを使いたいなら修正必要。

Q4: coordinate_system フィールドの必要性は?
    → グローバルモード検知時に SENSOR_LOCAL vs WORLD_ENU の判別に使う。
      当面は不要。
```

---

### 作業タイムライン

```
         Week 1           Week 2           Week 3           Week 4
    ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ Step 0   │     │          │     │          │     │          │
    │ Step 1   │     │ Step 2   │     │ Step 3   │     │ Step 3   │
    │          │     │ spatial- │     │ geo-     │     │ (cont.)  │
    │          │     │ grid     │     │ viewer   │     │ Step 4   │
    │          │     │ テスト    │     │ CesiumJS │     │ Step 5   │
    └──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                        ▼
                                                      両方動作確認 ✓
                                                        ▼
                                                      Step 6: Python 協議
```

| Step | 所要時間 |
|---|---|
| Step 0: 環境復旧 | 10 分 |
| Step 1: 設定追加 | 30 分 |
| Step 2: spatial-grid | 3-4 日 |
| Step 3: geo-viewer | 5-7 日 |
| Step 4: start.sh | 1-2 時間 |
| Step 5: 動作確認 | 半日 |
| **合計** | **約 2.5 週間** |

### 依存関係（実行順序）

```
Step 0 ─→ Step 1 ─→ Step 2 ─→ Step 3 ─→ Step 4 ─→ Step 5
                                 ▲
                                 │
                       API キー取得は並行可
                       (Step 2 中に取得開始)
```

> **並行作業可:** Step 2 と並行して CesiumJS の学習・プロトタイプ作成、API キー取得が可能。

### ビジュアライザ実装のリスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| CesiumJS 65k 点/フレームで遅い | geo-viewer カクつく | 間引き (10k 点) or フレームレート制限 (5 Hz) |
| Google 3D Tiles が Jetson で重い | GPU メモリ不足 | terrain のみ使用 (3D 建物なし) にフォールバック |
| Cesium Ion Token 取得に時間がかかる | Step 3 ブロック | 早めにアカウント作成 (Step 2 開始時) |
| CoordinateTransformer のバグ | 点群が変な位置に | 既知座標テストで早期検出 |
| webpack CesiumJS バンドルが複雑 | ビルド失敗 | cesium-webpack-example を参考に |

---

## リスク管理

### 高リスク要因

| # | リスク | 発生確率 | 影響度 | 対策 |
|---|---|---|---|---|
| R1 | vendor/alogs CJS → ESM 互換性 | 高 | 高 | createRequire で CJS ラップ、または esbuild で preprocess |
| R2 | 座標変換精度が要件を満たさない | 中 | 高 | Phase 2c で実地調査、GPS-RTK 検討、キャリブレーション自動化 |
| R3 | グローバルボクセルの解像度選択が性能に影響 | 中 | 中 | unit_m パラメータのベンチマーク、デフォルト 10m で開始 |
| R4 | Google Maps API 月額課金が予想外 | 中 | 中 | 無料枠内の推定: ~10-20k requests/day，月100万で十分。キャッシング検討 |

### 中リスク要因

| # | リスク | 対策 |
|---|---|---|
| R5 | Cesium Ion 依存性 | self-hosted Cesium オプションも検討 |
| R6 | WebSocket データ古いが多すぎる（遅延） | フレームスキップアルゴリズム導入 |
| R7 | TypeScript 型安全性（sensor config） | Jest テストで network payload の validation |
| R8 | Jetson (ARM/Maxwell or Pascal GPU) での CesiumJS + WebGL 性能 | Jetson の GPU メモリ制限 (2-8GB)。Chromium on ARM での WebGL 制限あり。Google 3D Tiles が重すぎる場合は terrain のみにフォールバック。初期段階で Jetson 実機での動作検証を実施すること |

---

## 時間見積もり

| Phase | 主要タスク | 開発時間 | リード | 実装順 |
|---|---|---|---|---|
| **2a** | マウント情報管理 | 1-2 週間 | 初級開発者 | parallel-ready |
| **2b** | 座標変換 + 空間IDユーティリティ | 2-3 週間 | 中級開発者（数学知識） | 2a 完了後 |
| **2c** | キャリブレーション検証 | 2-3 週間 | シニア開発者 + 実地調査 | 2b 完了後 |
| **3a** | グローバルモード検知パイプライン | 3-4 週間 | 中級 TypeScript | 2b 完了後 |
| **3b** | Geo-viewer (CesiumJS) | 3-4 週間 | 中級 Cesium 開発者 | 3a 完了後 |
| **3c** | UI・キャリブレーションパネル | 2 週間 | フロントエンド開発者 | 3b 並行可 |
| **合計** | | **13-18 週間** | チーム体制で 3-4.5 ヶ月 | |

> **注:** 上記見積もりは全 Phase を順次実施する場合の最大値。
> [両ビジュアライザ動作確認手順](#両ビジュアライザ動作確認-実装手順python-変更なし方針) の Step 0〒5 のみを実施する場合は約 2.5 週間（Phase 2a + Phase 2bの一部 + Phase 3bの一部）。

**クリティカルパス:** Phase 2b → 2c → 3a → 3b（最短 10-14 週間）

---

## テスト戦略

### ユニットテスト

```bash
# spatial-grid モジュール
spatial-grid/tests/
  ├── euler-quaternion.test.ts     (座標変換の数学)
  ├── coordinate-transform.test.ts (既知点での精度)
  └── types.test.ts               (設定スキーマ)

# geo-viewer モジュール  
geo-viewer/tests/
  ├── cesium-integration.test.ts   (Google 3D Tiles 接続)
  ├── point-cloud-layer.test.ts    (ポイント更新速度)
  └── calibration-panel.test.ts    (UI イベント)

npm run test  (Jest で全テスト実行)
```

### 統合テスト

```
start.sh で全システム起動後:
  1. WebSocket → detector → geo-viewer データフロー
  2. 侵入検知結果が Cesium 上に表示されるか
  3. キャリブレーションスライダーで heading 変更時に点群が回転するか
```

### 実地検証テスト

```
明石市立天文科学館での実測:
  1. 既知の建物角（GPS計測済み）の点をスキャン
  2. geo-viewer での表示座標と GPS 座標を比較
  3. <10m の誤差を目指す
```

---

## 深層レビュー：発見された問題点と必須修正事項

> 本章は、ロードマップ全体のコードベース検証により発見された
> **漏れ・重複・矛盾・考慮不足・曖昧・間違い・説明不足** を列挙し、
> 特に **Python 領域への最小限の必須変更** を詳述する。

### 発見された問題の総覧

| # | 分類 | 場所 | 問題 | 深刻度 | ステータス |
|---|------|------|------|--------|------------|
| P1 | **漏れ** | ロードマップ全体 | Python 側の変更が一切記載されていない → Phase 2a〜2bは案A(二重管理)で開始、Phase 3aで Py-1〜Py-5 実施 | **致命的** | ✅ 対応済み（段階的方針で解決） |
| P2 | **漏れ** | WebSocket ペイロード | `installation` (lat/lon/alt) が送信されていない → Phase 3a で対応。Phase 2a は Node.js sensors.json から取得 | **致命的** | ✅ 段階的対応計画策定済み |
| P3 | **漏れ** | 設定の単一ソース | mount 情報の二重管理問題 → start.sh で Python config から自動生成で整合性保証 | **高** | ✅ 解決策記載済み |
| P4 | **間違い** | Phase 2b 座標変換の数学 | ENU→ECEF 回転行列が欠落していた | **高** | ✅ **修正済み** — コード例に `computeENUtoECEF()` 実装。極地安定性ガード追加 |
| P5 | **重複** | `coordinates.py` vs `coordinate-transform.ts` | WGS84⇔ECEF 変換が Python/TypeScript で二重実装 | **中** | ℹ️ 許容（テストで相互比較） |
| P6 | **漏れ** | `ouster_pcap_replay.py` | `json.dumps` バイパス — `_frame_to_json()` 拡張が反映されない | **高** | ✅ Py-3 で CepfFrame 経由に修正予定 |
| P7 | **間違い** | vendor/alogs API | `.default` アクセスパターンの実行時検証が必要 | **中** | ℹ️ Phase 2b テストで検証 |
| P8 | **考慮不足** | `CoordinateSystem` enum | `WORLD_ENU` / `WORLD_ECEF` の変換ロジック未実装 | **低** | ℹ️ 将来対応 |
| P9 | **曖昧** | `CepfPoints` 型 | lat/lng/alt フィールド未定義 | **低** | ℹ️ 将来対応 |
| P10 | **漏れ** | `_frame_to_json()` timestamp | PCAP タイムスタンプとの不整合 | **低** | ℹ️ 将来対応 |
| **P11** | **間違い** | `intrusion-detector.ts` | `evaluate()` が `bgStddev=0` を常に渡す — `AdaptiveStddevThreshold` の sigma パラメータが実質無効 | **高** | ⚠️ **要コード修正** — `VoxelDiffEntry` に `backgroundStddev` フィールド追加が必要 |
| **P12** | **漏れ** | `ws-client/types.ts` | `FrameMessage` に `type` フィールドがない — config メッセージ受信時にクラッシュする | **高** | ⚠️ Phase 3a で修正 |
| **P13** | **漏れ** | `BackgroundVoxelMap.isStable()` | 全ボクセルが `minSamples` を満たす必要があるが、新規ボクセルが毎フレーム追加されるため実運用で安定判定が困難 | **中** | ⚠️ 閾値ロジック改善を検討（例: 上位N%のボクセルで判定、または一定時間経過で強制安定化） |
| **P14** | **漏れ** | `GlobalVoxelGrid` | `keyToCenter()` メソッドが欠落 — `VoxelGridLike` インターフェースに含めるか検討必要 | **低** | ℹ️ Phase 3a で検討 |

---

### P1（致命的→✅ 解決済み）: Python 側の変更方針

**解決策:** Phase 2a〜2b では案A（Node.js 側で独立管理）で Python 無変更。
Phase 3a で Py-1〜Py-5 の最小変更を実施し案B（WebSocket 経由自動同期）に移行。
Phase 2a/2b チェックリストの Python 項目は「Phase 3a で実施」と明記済み。

**背景:** ロードマップは当初 Node.js/TypeScript 側の変更のみを記載しており、
Python 側は「変更なし」の前提で書かれていた。しかし実際は以下の Python 変更が**不可欠**。

#### なぜ Python 側の変更が必要か

```
現在のデータフロー:

  [Python]
  ouster_pcap_replay.py
    │ json.dumps({frame_id, timestamp, points:{x,y,z}})
    │
    ▼ WebSocket
    │
  [Node.js]
  main-detector.ts
    │ ← ここで座標変換したいが…
    │    installation (lat/lon/alt) の情報がない！
    │    heading/pitch/roll の情報もない！
    │
    ╳ GlobalVoxelGrid が構築できない
```

Node.js 側で座標変換を行うには、**センサー設置位置 (installation)** の情報が必要。
現在これは Python 側の `apps/sensors.example.json` にのみ存在し、
WebSocket ペイロードには含まれていない。

#### 解決策の選択肢

| 案 | 説明 | Python 変更量 | メリット | デメリット |
|---|---|---|---|---|
| **A: Node.js 側で独立管理** | `apps_ts/sensors.json` に `mount` を手動記入 | **なし** | Python 完全無変更 | 二重管理、設定ズレのリスク |
| **B: WebSocket 初回メッセージ** | Python→Node.js に `installation` を初回接続時に送信 | **最小** | 単一ソース、自動同期 | WebSocket プロトコル拡張 |
| **C: 共有設定ファイル** | 1つの JSON をPython/Node.js 双方から読む | **小** | 完全な整合性 | ファイルパス管理が複雑 |

**推奨: 案 A（Phase 2a）→ 案 B（Phase 3a）への段階的移行**

Phase 2a では最小変更の案 A で開始し、Phase 3a でプロトコル拡張（案 B）を行う。

---

### P2（致命的）: WebSocket ペイロード拡張

#### 現在のペイロード

```json
// ← ouster_pcap_replay.py が送信する現在のフォーマット
{
  "frame_id": 42,
  "timestamp": 1741272000.123,
  "points": {
    "x": [1.0, 2.0, ...],
    "y": [0.5, 1.5, ...],
    "z": [3.0, 4.0, ...]
  }
}
```

#### Phase 3a で必要なペイロード

```json
{
  "type": "frame",              // ← NEW: メッセージタイプ識別子
  "frame_id": 42,
  "timestamp": 1741272000.123,
  "points": {
    "x": [1.0, 2.0, ...],
    "y": [0.5, 1.5, ...],
    "z": [3.0, 4.0, ...]
  }
}
```

加えて、接続時に1回だけ送信する設定メッセージ：

```json
// ← Python が WebSocket 接続確立時に1回送信
{
  "type": "config",
  "installation": {
    "reference_latitude": 34.649394,
    "reference_longitude": 135.001478,
    "reference_altitude": 54.0,
    "reference_datum": "WGS84",
    "sensor_offset": [0.0, 0.0, 1.0]
  },
  "transform": {
    "translation": [0.0, 0.0, 0.0],
    "rotation_quaternion": [1.0, 0.0, 0.0, 0.0]
  },
  "coordinate_system": "sensor_local"
}
```

**Node.js 側の処理:**
- `type === "config"` → `installation` を保存、`GlobalVoxelGrid` のマウント情報として使用
- `type === "frame"` → 従来通り点群処理
- `type` フィールドがない（旧フォーマット）→ `"frame"` として処理（後方互換性）

---

### P3（高）: 設定ファイルの単一ソース化

#### 現状の問題

```
apps/sensors.example.json (Python 側):
  ├── sensors[]                        ← センサー設定の配列（7エントリ）
  │   ├── sensor_id, parser_name, config  ← Python 固有
  │   └── transform                        ← heading/pitch/roll 相当
  └── installation                     ← lat/lon/alt (WGS84) ※ルートレベル

apps_ts/sensors.example.json (Node.js 側):
  ├── websocket_url                    ← Node.js 固有
  ├── voxel_cell_size                  ← Node.js 固有
  └── detector                         ← Node.js 固有
```

**`installation` は Python 側にしか存在しない。** ロードマップでは
Node.js 側の `sensors.json` に `mount` ブロックを追加する計画だが、
これは Python 側の `installation` と**同じ情報の二重管理**になる。

#### 最小変更の解決策

Phase 2a では二重管理を許容しつつ、`start.sh` で整合性を保証する：

```bash
# start.sh に追加するロジック（Phase 2a）
# Python 側の installation から Node.js 側の mount を自動生成

PYTHON_CONFIG="apps/sensors.example.json"
TS_SENSORS="apps_ts/sensors.json"

# Python 設定から installation を抽出
INSTALL_LAT=$(python3 -c "import json; d=json.load(open('$PYTHON_CONFIG')); print(d.get('installation',{}).get('reference_latitude', 0))")
INSTALL_LNG=$(python3 -c "import json; d=json.load(open('$PYTHON_CONFIG')); print(d.get('installation',{}).get('reference_longitude', 0))")
INSTALL_ALT=$(python3 -c "import json; d=json.load(open('$PYTHON_CONFIG')); print(d.get('installation',{}).get('reference_altitude', 0))")

# Node.js sensors.json に mount ブロックを注入
python3 -c "
import json
with open('$TS_SENSORS') as f:
    cfg = json.load(f)
cfg['mount'] = {
    'position': {'lat': $INSTALL_LAT, 'lng': $INSTALL_LNG, 'alt': $INSTALL_ALT},
    'orientation': {'heading': 0.0, 'pitch': 0.0, 'roll': 0.0}
}
with open('$TS_SENSORS', 'w') as f:
    json.dump(cfg, f, indent=2)
"
```

---

### ~~P4（高）: 座標変換の数学的誤り~~ — ✅ 修正済み

> **ステータス:** Phase 2b のコード例（`coordinate-transform.ts`）を修正済み。
> 元の問題: 回転後のセンサーローカル座標を直接 ECEF に加算していた。
> 修正内容: 4ステップ（Sensor→ENU→ECEF変位→ECEF加算→WGS84）を正しく実装。
> `computeENUtoECEF()` メソッドで ENU→ECEF 回転行列をコンストラクタで事前計算。
> `ecefToLatLngAlt()` に極地付近での数値安定性ガード（`cos_lat > 1e-10`）を追加。

---

### P5（重複）: Python の既存座標変換ユーティリティ

`cepf_sdk/utils/coordinates.py` に既に実装済みの関数：

| 関数 | 実装状態 | TypeScript 側の対応 |
|---|---|---|
| `lla_to_ecef(lat, lon, alt)` | ✅ 完成 | `coordinate-transform.ts` で再実装（重複） |
| `ecef_to_lla(x, y, z)` | ✅ 完成 (Bowring) | `coordinate-transform.ts` で再実装（重複） |
| `spherical_to_cartesian()` | ✅ 完成 | 不要（LiDAR SDK がパース時に変換済み） |

**方針:** 重複実装は許容する。理由：
1. Python 側は将来のサーバーサイド処理用（ログ、DB 保存）
2. TypeScript 側はリアルタイムクライアント処理用
3. 同一言語内での重複ではなく、Python/TypeScript 間の並行実装
4. WGS84 定数は標準値なので実装の一致は自明

ただし、**テスト時に Python と TypeScript の出力を相互比較**して
実装の整合性を検証すべき（Phase 2b チェックリストに追加）。

---

### P6（高）: `ouster_pcap_replay.py` のバイパス問題

#### 現状

`ouster_pcap_replay.py` は `WebSocketTransport.send(frame)` を**使っていない**。
代わりに `json.dumps()` で直接 JSON を構築し、`ws.send()` で送信している。

```python
# ouster_pcap_replay.py L200-209（現在のコード）
payload_str = json.dumps({
    "frame_id": frame_id,
    "timestamp": float(ts),
    "points": {
        "x": pts[:, 0].tolist(),
        "y": pts[:, 1].tolist(),
        "z": pts[:, 2].tolist(),
    },
})
# ... transport._clients に直接送信
```

**問題:** `WebSocketTransport._frame_to_json()` を拡張しても
`ouster_pcap_replay.py` には反映されない。

#### 必須修正

`ouster_pcap_replay.py` を修正して `CepfFrame` + `WebSocketTransport.send()` を
経由するようにする。これにより：
1. ペイロードフォーマットの一元管理
2. `installation` メタデータの自動付与
3. 将来の拡張（フィルター適用など）に対応

---

### P7（中）: vendor/alogs の API 呼び出し検証

#### 確認結果

`Encode.d.ts` の実際のシグネチャ:

```typescript
// ✅ 存在する — ロードマップの記述は正しい
static LatLngTo3DID(lat: number, lng: number, alt: number, unit?: number): string;
```

```typescript
// ✅ 存在する
static gridIdTo3DLocation(address: string): IGrid3D;
```

ただし注意点:
- `Encode.js` は `exports.__esModule = true` + `Object.defineProperty` で
  CommonJS エクスポートしている
- `createRequire()` で読み込んだ場合 `.default` が必要かどうかは
  runtime で確認が必要（`module.exports = Encode` なのか
  `exports.default = Encode` なのかで異なる）
- **Phase 2b で実際に動作確認テストを書くこと** がリスク軽減になる

---

### Python 側の最小必須変更一覧

以下は Phase 2a〜3a で必要な Python 側の変更を**最小限**に絞ったもの。

#### 変更 Py-1: `_frame_to_json()` に `type` フィールド追加

**ファイル:** `cepf_sdk/transport/websocket_server.py`

```python
# 変更前
payload = {
    "frame_id": frame.metadata.frame_id,
    "timestamp": time.time(),
    "points": points_dict,
}

# 変更後（後方互換あり）
payload = {
    "type": "frame",                           # ← 追加
    "frame_id": frame.metadata.frame_id,
    "timestamp": time.time(),
    "points": points_dict,
}
```

**影響範囲:** Node.js 側の既存コードは `type` フィールドを無視するため後方互換。
変更量: **1行追加**。

#### 変更 Py-2: `WebSocketTransport` に config メッセージ送信機能追加

**ファイル:** `cepf_sdk/transport/websocket_server.py`

```python
class WebSocketTransport:
    def __init__(self, host, port, installation=None, transform=None):
        # ... 既存コード ...
        self._installation = installation     # ← 追加
        self._transform = transform           # ← 追加

    async def _handler(self, websocket):
        self._clients.add(websocket)
        # ── 接続時に config メッセージを送信 ──
        if self._installation:
            config_msg = json.dumps({
                "type": "config",
                "installation": self._installation,
                "transform": self._transform,
            })
            await websocket.send(config_msg)
        # ── 以降は既存コード ──
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)
```

**変更量:** コンストラクタに引数2つ追加、`_handler` に 5行追加。

#### 変更 Py-3: `ouster_pcap_replay.py` を `CepfFrame` 経由に修正

**ファイル:** `apps/ouster_pcap_replay.py`

```python
# 変更前: json.dumps() で直接送信
payload_str = json.dumps({
    "frame_id": frame_id,
    "timestamp": float(ts),
    "points": { "x": pts[:, 0].tolist(), ... },
})
for ws in transport._clients:
    await ws.send(payload_str)

# 変更後: CepfFrame → WebSocketTransport.send() 経由
from cepf_sdk.frame import CepfFrame, CepfMetadata

metadata = CepfMetadata(
    timestamp_utc=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
    frame_id=frame_id,
    coordinate_system="sensor_local",
    coordinate_mode="cartesian",
    units={"distance": "m"},
)
# CepfFrame は format, version, metadata, schema, points, point_count が全て必須
frame = CepfFrame(
    format="CEPF",
    version="1.4",
    metadata=metadata,
    schema={"x": "float64", "y": "float64", "z": "float64"},
    points={"x": pts[:, 0], "y": pts[:, 1], "z": pts[:, 2]},
    point_count=len(pts),
)
await transport.send(frame)
```

**変更量:** 15行前後の書き換え。
**メリット:** `_frame_to_json()` の拡張が自動的に反映される。

#### 変更 Py-4: `ouster_pcap_replay.py` の `WebSocketTransport` 初期化で `installation` を渡す

**ファイル:** `apps/ouster_pcap_replay.py`

```python
# installation を設定ファイルまたは CLI 引数から取得
import json

installation = None
if args.config:
    with open(args.config) as f:
        cfg = json.load(f)
    installation = cfg.get("installation")
    transform = cfg.get("transform")

transport = WebSocketTransport(
    host=host, port=port,
    installation=installation,    # ← 追加
    transform=transform,          # ← 追加
)
```

**変更量:** 10行前後の追加。CLI に `--config` 引数を追加。

#### 変更 Py-5: `start.sh` の PCAP リプレイ起動コマンドに `--config` を追加

**ファイル:** `start.sh`

```bash
# 変更前
python3 apps/ouster_pcap_replay.py --pcap ... --meta ...

# 変更後
python3 apps/ouster_pcap_replay.py --pcap ... --meta ... \
    --config apps/sensors.example.json
```

**変更量:** 1行修正。

---

### 変更量の総括

| 変更ID | ファイル | 変更量 | Phase |
|--------|---------|--------|-------|
| Py-1 | `cepf_sdk/transport/websocket_server.py` | +1 行 | 2a |
| Py-2 | `cepf_sdk/transport/websocket_server.py` | +10 行 | 3a |
| Py-3 | `apps/ouster_pcap_replay.py` | ~15 行書き換え | 2a |
| Py-4 | `apps/ouster_pcap_replay.py` | +10 行 | 3a |
| Py-5 | `start.sh` | +1 行 | 3a |
| **合計** | | **~37 行** | |

**Python SDK のコア (`cepf_sdk/`) への変更は計 11 行のみ。**
残りは `apps/ouster_pcap_replay.py`（アプリケーション層）と `start.sh`。

---

### Phase 別の Python 変更タイミング

```
Phase 2a〜2b（Python 変更なし — 案A: 二重管理で開始）:
  ※ Node.js 側の sensors.json に mount ブロックを追加して運用

Phase 3a（グローバルモード実装時 — 案B に移行）:
  Py-1  _frame_to_json() に "type": "frame" 追加 (1 行)
  Py-2  WebSocketTransport に config メッセージ送信機能追加 (10 行)
  Py-3  ouster_pcap_replay.py を CepfFrame 経由に修正 (15 行)
  Py-4  ouster_pcap_replay.py に --config 引数追加 (10 行)
  Py-5  start.sh に --config 引数追加 (1 行)
  ※ この時点で案B（WebSocket 経由の自動同期）に移行

Node.js 側の対応:
  Phase 2a: mount 情報は sensors.json から取得（WebSocket 非依存）
  Phase 3a: "type" フィールドの存在チェック追加（後方互換）
  Phase 3a: "config" メッセージのパース → mount 情報として使用
```

---

### 追加で必要なテスト

| テスト | 内容 | Phase |
|--------|------|-------|
| Python/TS 座標変換相互比較 | `lla_to_ecef()` (Python) と `latLngAltToECEF()` (TS) の出力を10点以上で比較 | 2b |
| WebSocket プロトコル互換性 | `"type"` フィールドあり/なしの両方を Node.js 側が正しく処理するか | 2a |
| `vendor/alogs` CJS ロード | `createRequire()` で `Encode.default` vs `Encode` のどちらが正しいか | 2b |
| `config` メッセージ受信 | Node.js 側が `"type": "config"` を正しくパースして `mount` 情報を構築できるか | 3a |
| ENU→ECEF 変換行列 | 明石市(北緯34°)での ENU 変位 [100, 0, 0] (東100m) が正しい ECEF 変位になるか | 2b |

---

## 成功基準

| Metric | 要件 | 測定方法 |
|---|---|---|
| 座標変換精度 | < 10 m @ 100 m | 実地テスト |
| フレーム処理速度 | >= 20 Hz | FPS 計測 |
| ポイント数 | >= 65k points | frame payload 分析 |
| API 応答時間 | < 100 ms | ネットワーク profiling |
| キャリブレーション手順 | < 30 分 | ユーザーテスト |
| ドキュメント完成度 | >= 90% | レビュー |

---

## まとめ

このロードマップは Phase 1 の成功を基盤に、以下を実現します：

1. **Phase 2a-2c:** ローカルグリッド（`voxel/`）に影響を与えずに、WGS84 座標変換基盤と空間IDユーティリティを実装
2. **Phase 3a:** グローバルモード検知パイプラインの構築 — `GlobalVoxelGrid` → `VoxelSnapshot` → 既存の `BackgroundVoxelMap` → `computeDiff` → `IntrusionDetector`（検知ロジック変更なし、グリッド層の差し替えのみ）
3. **Phase 3b-3c:** CesiumJS + Google Photorealistic 3D Tiles で地理的状況把握とインタラクティブキャリブレーション
4. **既存コードの保護:**
   - `voxel/` — `VoxelGridLike` インターフェース追加のみ（Phase 3a）（`keyToCenter()` は `VoxelGrid` に既存実装済み）
   - `detector/` — 変更なし
   - `viewer/` — **Phase 3a で以下の変更が必要:** `GlobalVoxelLayer` 追加、`config.json` fetch機構追加、侵入ハイライト受信機構追加
   - `ws-client/` — **Phase 3a で** `FrameMessage` に `type?` フィールド追加・`_parseMessage` に型分岐追加
5. **設計原則:** ローカル/グローバルは排他的選択。侵入検知の原理（背景学習→差分→閾値判定）は座標系に依存しない

**次のアクション:**
- [ ] Phase 2a タスク分析・チームアサイン
- [ ] spatial-grid パッケージ初期化（npm init, tsconfig.json）
- [ ] sensors.example.json スキーマレビュー（mount ブロック追加）
- [ ] vendor/alogs の CJS → ESM ラッパー動作確認
- [ ] Google Cloud Console + Cesium Ion アカウント準備
- [ ] ⚠️ `intrusion-detector.ts` の stddev=0 問題を修正（P11 — `VoxelDiffEntry` に `backgroundStddev` 追加）
- [ ] ⚠️ `BackgroundVoxelMap.isStable()` の改善検討（P13）
- [ ] Jetson 実機での CesiumJS + WebGL 動作検証（R8）

> **実行方針 (2026-03-07 更新):**  
> Phase 2a〜2b は **Python 側を変更せず**（案A: 二重管理）Node.js 側のみで両ビジュアライザ（Three.js ローカル + CesiumJS 地球儀）を動作確認する。  
> Phase 3a で Python 側の最小変更 (Py-1〜Py-5, 計約37行) を実施し、案B（WebSocket 経由の自動同期）に移行する。  
> geo-viewer は**表示専用**とし、検知パイプラインは `main-detector.ts` に集約する。  
> 詳細手順 → [両ビジュアライザ動作確認 実装手順](#両ビジュアライザ動作確認-実装手順python-変更なし方針)（本ドキュメント内に統合済み）

---

## 実行方針の説明

**この方針は以下の優先順位に基づいています：**

1. **Phase 2a〜2b（リスク最小化）**  
   Python 側はそのまま。Node.js 側（`spatial-grid`, `viewer/`, `geo-viewer/`, `detector/`）のみで両ビジュアライザを動作確認。これにより既存の検知パイプライン（Python 側）への影響ゼロで新機能を検証できます。

2. **Phase 3a（Python 統合）**  
   検証完了後、Python 側に最小限の変更を加えます (`_frame_to_json()` に `type` フィールド追加等、約37行)。これで WebSocket 自動同期に移行。既存ロジック保護（`VoxelGridLike` インターフェース経由）により回帰テスト最小化。

3. **geo-viewer は表示専用**  
   検知ロジックは `main-detector.ts` に一元化。geo-viewer は WebSocket から受信した IntrusionEvent をリアルタイム表示するのみ。これにより：
   - ロジック重複排除（不一致防止）
   - Node.js 側の createRequire（ブラウザ非互換）の問題回避
   - CesiumJS での地理可視化に専念できる

**結果：** ローカル/グローバルモードの両方を同一 WebSocket フィードから並行動作（Three.js + CesiumJS）。

**最終更新:** 2026-03-07（深層レビュー指摘 22 件を反映）

---

## Claude Code への実行命令

### 実装範囲

**本指示では Phase 2b（座標変換レイヤー）までを対象とします。**

**この範囲で達成できること：**
- ✅ `spatial-grid/` パッケージの完全実装（座標変換 + 空間 ID ユーティリティ）
- ✅ `viewer/` と `geo-viewer/` が同一 PCAP フィードをリアルタイム受信・表示
- ✅ Three.js（ローカル座標系）と CesiumJS（地球儀）の**両ビジュアライザ同時動作確認**
- ✅ Python 側は一切変更しない（リスク最小化）
- ❌ 検知パイプラインのグローバルモード対応はまだ（Phase 3a で実施）

**実装ステップ（優先順位順）:**

| Step | 内容 | 所要時間 | 完了基準 |
|---|---|---|---|
| **0** | 環境復旧・ローカルビューワー動作確認 | 10 分 | `./start.sh` なし Point cloud がlocalhost:3000 に表示 |
| **1** | `apps_ts/sensors.example.json` に mount ブロック追加 | 1 時間 | `npm run build` 成功、型チェック OK |
| **2** | `spatial-grid/` パッケージ初期化 + types.ts 実装 | 3 時間 | Jest テスト 3+ 件合格 |
| **3** | `euler-quaternion.ts` 実装 | 4 時間 | Jest テスト 5+ 件合格、既知値での精度確認 |
| **4** | `coordinate-transform.ts` 実装 | 5 時間 | Jest テスト 10+ 件合格、性能テスト（1秒 65k 点） |
| **5** | `spatial-id-converter.ts` + vendor/alogs ESM ラッパー | 3 時間 | `npm run build` 成功、型チェック OK |
| **5b** | `geo-viewer/` パッケージ実装（CesiumJS） | 7-10 時間 | localhost:3001 で地球儀 + 点群表示、Three.js との並行動作確認 |
| **5c** | `start.sh` 更新（geo-viewer/config.json 自動生成、起動スクリプト） | 2 時間 | `./start.sh` で 2 つのビジュアライザ + PCAP 同時起動 |
| **6** | 両ビジュアライザ統合テスト（動作確認） | 1 時間 | http://localhost:3000 と http://localhost:3001 から同じ点群が見える |
| **7（オプション）** | Phase 2c キャリブレーション検証ツール | 3-5 時間 | `calibration-assistant.ts` コマンドライン実行可、heading 調整 UI 動作 |

**合計:** 25〜35 時間（Step 0-6 のみなら 25 時間）

---

### 関鍵チェックポイント

**実装前に確認事項:**

```bash
# 1. リポジトリ構造確認
ls -la /home/jetson/repos/sass/{apps_ts,spatial-grid,viewer,geo-viewer,voxel,detector}

# 2. vendor/alogs の存在確認
ls -la /home/jetson/repos/sass/vendor/alogs/

# 3. 既存 Node.js ビルド確認
cd /home/jetson/repos/sass/viewer && npm run build
cd /home/jetson/repos/sass/apps_ts && npm run build
```

**実装時の制約:**

1. ❌ **Python 側の一切の変更の禁止** — `cepf_sdk/`, `apps/` はそのまま
2. ✅ **Node.js 側のみで両ビジュアライザを動作** — config の二重管理許容（Phase 3a で統合）
3. ✅ **vendor/alogs は createRequire で読み込む** — ESM ラッパー経由
4. ⚠️ **のブラウザ互換:** `coordinate-transform.ts` は OK（Node.js API 不使用）、`spatial-id-converter.ts` はダメ（createRequire）
5. ⚠️ **detector/ の変更は Phase 3a で** — いまは検知パイプラインに GlobalVoxelGrid を接続しない

---

### 実装上の注意

**座標変換の精度:**
- WGS84 ↔ ECEF 変換: Heikkinen 反復法（5 回）で十分
- ENU → ECEF 回転行列: φ, λ だけで計算可能（マウント時に一度）
- Euler 角 → Quaternion: ZYX 順序（航法規約）を確認

**パフォーマンス:**
- CoordinateTransformer: 65k 点を 1 秒で処理可能なこと（性能テストで確認）
- GC 圧力: 点ごとに新 object 生成するのは避ける（事前に配列確保）

**ブラウザ互換性:**
- `geo-viewer/` の webpack では `coordinate-transform.ts` のみ import 可
- `spatial-id-converter.ts` を import してはダメ
- 代わりに `main-detector.ts` が IntrusionEvent をマウント情報込みで送信（Phase 3a）

---

### 成功基準（全クリア要件）

**完了時のチェックリスト:**

```
☐ Step 0: ローカルビューワー動作確認（reboot 後も）
☐ Step 1: sensors.example.json mount ブロック追加、npm run build 成功
☐ Step 2-4: spatial-grid/ 座標変換実装、Jest 20+ テスト合格
☐ Step 5: vendor/alogs ESM ラッパー、型チェック OK
☐ Step 5b: geo-viewer/ CesiumJS ビューワー、localhost:3001 で地球儀と点群表示
☐ Step 5c: start.sh 更新、./start.sh で 2 ビジュアライザ同時起動
☐ Step 6: 両ビジュアライザで同じ点群がリアルタイム表示される
    - localhost:3000: Three.js ローカル座標（センサー中心）
    - localhost:3001: CesiumJS 地球儀（WGS84）
    - 建物の位置・向き・高さが一致していること（heading=0° 時）
☐ リグレッション: ./start.sh --stop で全プロセス停止、Python 側に影響なし
```

**期待される出力例（start.sh 実行時）:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SASS 起動完了!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Python PCAP    ./apps/ouster_pcap_replay.py [demo.pcap]
  WebSocket      ws://0.0.0.0:8765
  Viewer         http://localhost:3000   (Three.js)
  Geo-Viewer     http://localhost:3001   (CesiumJS)
  Detector       ヘッドレス侵入検知ログ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[PCAP] Frame 1/1500...
[Viewer] Connected to WS, receiving frames at 20 Hz
[Geo-Viewer] Connected to WS, displaying points on Cesium
[Detector] (ローカルモード) 背景学習中... (30 フレーム)
```

---

### リスク & 対策

| リスク | 影響 | 対策 |
|---|---|---|
| vendor/alogs の CJS 読み込み失敗 | geo-viewer ビルド不可 | ESM ラッパーを createRequire で動作確認（Node.js のみ） |
| 座標変換精度不足 | Three.js と Cesium で点の位置がズレ | カリブレーション（heading 調整）→ Phase 2c |
| CesiumJS + Jetson GPU メモリ不足 | 3D Tiles 読み込み失敗 | Google Photorealistic 3D Tiles をスキップ、terrain のみで続行 |
| ネットワークレイテンシ | WebSocket フレーム落ち | バッファリング + ダウンサンプル（5 Hz） |
| npm 依存関係競合 | ビルド失敗 | package-lock.json 削除 → npm install |

---

### Phase 2c（オプション）実施判断基準

Phase 2b 完了時点で以下いずれかが満たされたら、Phase 2c（キャリブレーション）を実施：

- ☐ 実機（Jetson）での座標精度が ±5m 以内（測地測量で確認可能）
- ☐ heading カリブレーション補助ツールが必要（Google Maps 視覚照合）
- ☐ 建物・マンホール蓋など既知点が ±1m で一致する必要

否(予定通り Phase 3a へ) → Phase 3a で実装・テストを並行
