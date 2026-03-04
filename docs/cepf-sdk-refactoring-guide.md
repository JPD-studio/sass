# CEPF-SDK リファクタリング・実装ガイド

> **目的**: 現在の Airy 単体プロトタイプを、CEPF/USC 仕様書 v1.3 に準拠した **マルチセンサ対応の汎用 SDK** に再構築するための、AI への指示書・作業手順書。
> **対象**: AI コーディングアシスタント（例: GitHub Copilot, OpenAI Codex など）
>cepf-sdkとouster_bridgh3をベースとするが、repos/sass/の下に新規構築せよ。
>特にcepf_sdk/の中のコードは出来るだけ再利用すること。
>vendor/はそのまま使用し、決して修正してはならない。
> **重要**: 編集するのはrepos/sass/以下だけとせよ。repos/cepf-sdk/とrepos/ouster_bridge3とrepos/vendor/はあくまでも参考として、一切へんこうしてはならない。

>
> **作成日**: 2026-03-03  
> **基準仕様**: `docs/CEPF_USC_Specification_v1_3.md`（v1.3.0, 2026-03-03）
>上記の仕様書はすこし古くなっている。このファイルを最新として、コーディングと同時にrepos/sass/docs/CEPF_USC_Specification_v1_4.mdとして新規で作成せよ。

---

## 目次

1. [プロジェクトの現状分析](#1-プロジェクトの現状分析)
2. [目標フォルダ構成](#2-目標フォルダ構成)
3. [アーキテクチャ設計方針](#3-アーキテクチャ設計方針)
4. [USC（UnifiedSenseCloud）ファクトリークラスの設計](#4-uscunifiedsensecloudファクトリークラスの設計)
5. [パーサー設計](#5-パーサー設計)
6. [フィルター設計](#6-フィルター設計)
7. [実装 TODO（優先順位付き）](#7-実装-todo優先順位付き)
8. [各ファイルの実装仕様](#8-各ファイルの実装仕様)
9. [チェックリスト](#9-チェックリスト)
10. [用語集・参照情報](#10-用語集参照情報)

---

## 1. プロジェクトの現状分析

### 1.1 現在のフォルダ構成

```
cepf-sdk/
├── pyproject.toml
├── README.md
├── docs/
│   ├── readme.md
│   └── CEPF_USC_Specification_v1_2.md
├── cepf_sdk/                   # SDK コア
│   ├── __init__.py             #   CepfFrame, CepfMetadata を公開
│   ├── frame.py                #   CepfFrame, CepfMetadata データクラス
│   ├── types.py                #   CepfPoints, NDArray 型エイリアス
│   └── airy/                   #   RoboSense Airy 専用デコーダ
│       ├── __init__.py         #     UdpAiryDecoder, AiryDecodeConfig を公開
│       └── decoder.py          #     UDP 受信 + パケットデコード + CepfFrame 生成
├── apps/                       # アプリケーション
│   ├── __init__.py
│   ├── run_pipeline.py         #   Producer-Consumer パイプライン
│   ├── processor.py            #   後段処理ロジック
│   └── processing/
│       └── filters/
│           ├── __init__.py
│           └── range_filter.py #   CylindricalRangeFilter
└── cepf_sdk.egg-info/          # 自動生成
```

### 1.2 現状の良い点

| 項目 | 説明 |
|------|------|
| `cepf_sdk/` と `apps/` の分離 | ライブラリとアプリケーションが分かれている |
| `CepfFrame` / `CepfPoints` の列指向構造 | 仕様書 v1.2 の column-oriented 構造に合致 |
| `airy/` をサブパッケージ化 | センサ固有コードを分離する方針は正しい |
| `frozen=True` のデータクラス | イミュータブル設計でデータの一貫性を保護 |

### 1.3 仕様との乖離（問題点）

| # | 仕様の要件 | 現状 | 影響度 |
|---|-----------|------|--------|
| 1 | `UnifiedSenseCloud` ファクトリークラス（パーサー登録・forge メソッド） | **未実装** | 高 |
| 2 | `RawDataParser` 抽象基底クラス（`parse()`, `validate()` インターフェース） | **未実装** — `UdpAiryDecoder` は独自設計 | 高 |
| 3 | 列挙型（`SensorType`, `CoordinateSystem`, `CoordinateMode`, `PointFlag`） | **未実装** — 文字列ベタ書き | 中 |
| 4 | データクラス（`SensorConfig`, `Transform`, `InstallationInfo`） | **未実装** | 中 |
| 5 | ユーティリティ（座標変換関数、I/O、フィルタ生成関数） | 一部のみ（`CylindricalRangeFilter` は `apps/` 内） | 中 |
| 6 | エラー階層（`CEPFError` → `ParseError` → ...） | **未実装** | 中 |
| 7 | バイナリ形式の読み書き | **未実装** | 低（後回し可） |
| 8 | テスト | **ディレクトリなし** | 中 |

### 1.4 現在の `UdpAiryDecoder` の責任過多

現在の `UdpAiryDecoder` は、本来別々であるべき複数の責任を 1 クラスで担っている：

```
UdpAiryDecoder（現在の責任）
├── UDP ソケット管理      ← 本来どちらの仕事でもない（トランスポート層）
├── バイナリ解析          ← パーサーの仕事
├── 座標変換              ← パーサーの仕事
├── フレーム集約          ← USC 寄りの仕事
├── メタデータ付与        ← USC の仕事
└── CepfFrame 生成       ← パーサーの仕事
```

分離後の責任分担：

```
分離後（Airy の場合）：
  トランスポート層    → UDP 受信だけ（apps/ 側）
  ドライバー層       → パケットバイナリ解析 + 角度テーブル（自前実装）
  パーサー           → ドライバーの出力 → 座標変換 + CepfFrame 生成
  フレーム集約       → 複数パケットの時間集約（apps/ または USC 層）
  USC               → パーサー管理 + フィルタ + 座標系変換 + 統合

分離後（Ouster の場合）：
  トランスポート層    → ouster-sdk の open_source() が担当
  ドライバー層       → ouster-sdk（外部パッケージ）が全て担当
  パーサー           → LidarScan → XYZLut → CepfFrame（薄いラッパー）
  フレーム集約       → ouster-sdk が LidarScan 単位で提供済み
  USC               → パーサー管理 + フィルタ + 座標系変換 + 統合
```

**Airy vs Ouster の根本的な違い**:
- **Airy**: RoboSense が公式 SDK を提供していないため、パケット解析を **自前実装** する
- **Ouster**: 公式 `ouster-sdk` がパケット解析・座標変換を提供するため、**薄いラッパー** で済む

---

## 2. 目標フォルダ構成

### 2.1 完全なディレクトリツリー

```
cepf-sdk/
├── pyproject.toml
├── README.md
│
├── docs/
│   ├── readme.md                          # SDK 使い方ドキュメント
│   ├── CEPF_USC_Specification_v1_2.md     # CEPF/USC 仕様書
│   └── cepf-sdk-refactoring-guide.md      # 本ドキュメント
│
├── cepf_sdk/                              # ========== SDK コア ==========
│   ├── __init__.py                        #   公開 API（CepfFrame, USC, etc.）
│   ├── frame.py                           #   CepfFrame, CepfMetadata
│   ├── types.py                           #   CepfPoints, NDArray 型エイリアス
│   ├── enums.py                           # 🆕 SensorType, CoordinateSystem,
│   │                                      #      CoordinateMode, PointFlag
│   ├── config.py                          # 🆕 SensorConfig, Transform,
│   │                                      #      InstallationInfo
│   ├── errors.py                          # 🆕 CEPFError, ParseError, etc.
│   ├── usc.py                             # 🆕 UnifiedSenseCloud メインクラス
│   │
│   ├── drivers/                            # ---- センサ固有ドライバー ----
│   │   ├── __init__.py
│   │   └── robosense_airy_driver.py       # 🆕 Airy パケットデコード（自前実装）
│   │                                      #     _decode_packet_cols() + 定数群
│   │                                      #     decoder.py のバイナリ解析部分を移植
│   │
│   ├── parsers/                           # ---- パーサー群 ----
│   │   ├── __init__.py                    #   公開 API + パーサー登録マップ
│   │   ├── base.py                        # 🆕 RawDataParser 抽象基底クラス
│   │   ├── robosense_airy.py              # 🆕 RoboSense Airy（drivers/ を呼ぶ）
│   │   ├── ouster_dome128.py              # 🆕 Ouster Dome 128（ouster-sdk ラッパー）
│   │   ├── ouster.py                      # 🆕 Ouster OS 共通基底（ouster-sdk ラッパー）
│   │   ├── velodyne.py                    # 🆕 Velodyne VLP-16/32C（実装済み）
│   │   ├── ti_radar.py                    # 🆕 TI AWR/IWR（実装済み: AWR1843/IWR6843）
│   │   └── continental.py                 # 🆕 Continental ARS（将来）
│   │
│   ├── filters/                           # ---- フィルター群 ----
│   │   ├── __init__.py                    #   公開 API（全フィルター re-export）
│   │   ├── base.py                        # 🆕 PointFilter, FilterMode, FilterResult
│   │   ├── pipeline.py                    # 🆕 FilterPipeline
│   │   │
│   │   ├── range/                         #   領域カット系
│   │   │   ├── __init__.py
│   │   │   ├── cylindrical.py             # 🆕 円筒形
│   │   │   ├── spherical.py               # 🆕 球形
│   │   │   ├── box.py                     # 🆕 直方体（AABB）
│   │   │   └── polygon.py                 # 🆕 多角形柱
│   │   │
│   │   ├── statistical/                   #   統計系（外れ値除去）
│   │   │   ├── __init__.py
│   │   │   ├── ror.py                     # 🆕 Radius Outlier Removal
│   │   │   ├── sor.py                     # 🆕 Statistical Outlier Removal
│   │   │   └── voxel.py                   # 🆕 ボクセルダウンサンプリング
│   │   │
│   │   ├── attribute/                     #   属性値ベース
│   │   │   ├── __init__.py
│   │   │   ├── intensity.py               # 🆕 強度フィルタ
│   │   │   ├── confidence.py              # 🆕 信頼度フィルタ
│   │   │   └── flag.py                    # 🆕 フラグベースフィルタ
│   │   │
│   │   └── classification/                #   分類・ラベリング
│   │       ├── __init__.py
│   │       ├── ground.py                  # 🆕 地面検出
│   │       └── noise.py                   # 🆕 ノイズ検出
│   │
│   ├── utils/                             # ---- ユーティリティ ----
│   │   ├── __init__.py
│   │   ├── coordinates.py                 # 🆕 spherical⇔cartesian, lla⇔ecef
│   │   ├── quaternion.py                  # 🆕 クォータニオン⇔回転行列
│   │   └── io.py                          # 🆕 load/save CEPF, to_pcd, to_las
│   │
│   └── airy/                              # ---- 後方互換ラッパー ----
│       ├── __init__.py                    #   既存コードが壊れないよう維持
│       └── decoder.py                     #   → parsers/robosense_airy.py に委譲
│
├── apps/                                  # ========== アプリケーション ==========
│   ├── __init__.py
│   ├── run_pipeline.py                    #   パイプラインエントリーポイント
│   ├── processor.py                       #   後段処理ロジック
│   └── processing/                        #   （将来 cepf_sdk/filters/ に統合）
│       └── filters/
│           ├── __init__.py
│           └── range_filter.py            #   既存の CylindricalRangeFilter
│
└── tests/                                 # ========== テスト ==========
    ├── __init__.py
    ├── test_frame.py
    ├── test_enums.py
    ├── test_usc.py
    ├── test_parsers/
    │   ├── __init__.py
    │   ├── test_robosense_airy.py
    │   └── test_ouster.py
    ├── test_filters/
    │   ├── __init__.py
    │   ├── test_cylindrical.py
    │   ├── test_ror.py
    │   └── test_pipeline.py
    └── test_utils/
        ├── __init__.py
        └── test_coordinates.py
```

### 2.2 `cepf_sdk/` 直下のサブフォルダ一覧

| フォルダ | 役割 |
|---------|------|
| `drivers/` | センサ固有のバイナリパケット解析ロジック。センサのプロトコル定数・デコード処理を担う。CepfFrame の存在を知らない最下層。自前実装のセンサのみ（Airy 等）。外部 SDK を使うセンサ（Ouster 等）は対応するファイルなし。 |
| `parsers/` | ドライバー（または外部 SDK）を呼び出し、センサデータを `CepfFrame` に変換するアダプタ層。センサごとに 1 ファイル。抽象基底クラス `base.py` を継承して実装する。 |
| `filters/` | 点群に対するフィルタリング処理。領域カット（`range/`）・統計的外れ値除去（`statistical/`）・属性値ベース（`attribute/`）・分類（`classification/`）の 4 種類のサブフォルダに分類される。センサの種類を知らない。 |
| `utils/` | 座標変換・クォータニオン計算・ファイル I/O など、センサ・フィルタに依存しない汎用数学ユーティリティ。 |
| `airy/` | **後方互換ラッパー**。既存コードが壊れないよう維持するためだけに残す。内部処理は `parsers/robosense_airy.py` に委譲する。新規コードからは使用しない。 |

### 2.3 各ディレクトリの責任マトリクス

| ディレクトリ | 何を知っているか | 何を知らないか |
|--|--|--|
| `types.py` / `frame.py` | CEPF データ構造 | センサ、フィルタの存在 |
| `enums.py` / `config.py` | 設定項目の定義 | 具体的なセンサ・処理 |
| `drivers/` | 特定センサのパケット構造・定数 | CepfFrame、他センサ |
| `parsers/` | ドライバー/外部 SDK の呼び方 + CepfFrame 生成 | 他のセンサ、フィルタ |
| `filters/` | 点群の幾何・統計条件 | センサの種類 |
| `utils/` | 数学・IO の汎用処理 | センサ、フィルタ |
| `usc.py` | パーサーとフィルタの組み合わせ方 | 各パーサーの内部実装 |
| `apps/` | ユースケース固有のロジック | SDK の内部実装 |

> **`drivers/` と `parsers/` の違い**:
> - `drivers/` = センサ固有のバイナリ解析ロジック。CepfFrame を知らない。自前実装のもの（Airy 等）のみ入る。
> - `parsers/` = ドライバーまたは外部 SDK を使い、CepfFrame に変換するアダプタ。
> - Ouster の場合、ドライバーは `ouster-sdk`（外部パッケージ）なので `drivers/` には何も入らない。

### 2.4 依存関係マップ

```
                    enums.py  config.py  errors.py
                       ↓         ↓         ↓
types.py ──→ frame.py ←─────────┘
                ↑
    ┌───────────┼───────────────────────┐
    │           │                       │
drivers/     parsers/     filters/                utils/
 airy_drv      base.py      base.py              coordinates.py
    ↑           ↑           ↑                   quaternion.py
    │           │           │                      io.py
    └──→ airy.py        range/cylindrical.py
     ouster.py ←── ouster-sdk (外部)
        ...     statistical/ror.py
                    ...
    │           │
    └─────┬─────┘
          ↓
       usc.py          ← 全部をまとめるファクトリー
          ↓
       apps/            ← SDK を使うアプリケーション
```

### 2.4 pyproject.toml の変更

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "cepf-sdk"
version = "0.2.0"
description = "CEPF SDK — UnifiedSenseCloud multi-sensor point-cloud library"
requires-python = ">=3.10"
dependencies = [
    "numpy",
    "scipy",       # ROR/SOR の cKDTree 用
]

[project.optional-dependencies]
dev    = ["pytest", "pytest-cov"]
io     = ["laspy"]                    # LAS 形式出力用
ouster = ["ouster-sdk>=0.13"]         # Ouster LiDAR パーサー用（公式 SDK）
all    = ["ouster-sdk>=0.13", "laspy"]

[tool.setuptools.packages.find]
include = ["cepf_sdk*"]
```

### 2.5 アプリケーション層の設定ファイル（推奨パターン）

**重要な設計原則:**
- **`cepf_sdk/` は変更しない** — SDK はプログラマーが変更禁止の "ブラックボックス"
- **設定ファイルはアプリ層に置く** — `apps_py/` と `apps_ts/` が各自の環境に合わせて管理
- **JSON 形式で外部化** — ハードコード不要、環境ごとに設定を切り替え可能

#### フォルダ構造

```
sass/
├── cepf-sdk/                    # ← SDK パッケージ（変更禁止）
│   ├── cepf_sdk/
│   └── pyproject.toml
│
├── apps_py/                     # ← プログラマーの専有領域
│   ├── run_pipeline.py          # エントリーポイント
│   ├── processor.py
│   ├── sensors.json             # ← 本番環境設定（.gitignore に追加推奨）
│   └── sensors.example.json     # ← テンプレート（Git 管理）
│
└── apps_ts/                     # ← TypeScript アプリ同様の設定
    ├── main-viewer.ts
    ├── sensors.json             # ← 本番環境設定
    └── sensors.example.json     # ← テンプレート
```

#### `sensors.json` のテンプレート例

**apps_py/sensors.example.json:**

```json
{
  "sensors": [
    {
      "sensor_id": "lidar_north",
      "parser_name": "robosense_airy",
      "config": {
        "sensor_type": "LIDAR",
        "model": "RoboSense Airy",
        "serial_number": "RS20250101",
        "firmware_version": "2.3.1",
        "num_channels": 32,
        "horizontal_fov_deg": 360.0,
        "vertical_fov_deg": 25.0,
        "max_range_m": 200.0,
        "range_resolution_m": 0.1
      },
      "transform": {
        "translation": [1.0, 0.0, 0.5],
        "rotation_quaternion": [0.707, 0.0, 0.707, 0.0]
      }
    },
    {
      "sensor_id": "lidar_south",
      "parser_name": "ouster_dome128",
      "config": {
        "sensor_type": "LIDAR",
        "model": "Ouster Dome 128",
        "max_range_m": 120.0
      }
    }
  ],
  "installation": {
    "reference_description": "ビル屋上東側にマウント",
    "reference_latitude": 35.6762,
    "reference_longitude": 139.6503,
    "reference_altitude": 220.5,
    "reference_datum": "WGS84",
    "sensor_offset": [1.5, 0.2, 0.3],
    "sensor_offset_description": "屋上コンクリート基準点からの相対位置"
  }
}
```

#### `.gitignore` の推奨設定

```gitignore
# アプリ層の環境固有設定
apps_py/sensors.json
apps_ts/sensors.json
apps_py/secrets.json
apps_ts/secrets.json

# テンプレートはGit管理OK
!apps_py/sensors.example.json
!apps_ts/sensors.example.json
```

#### `run_pipeline.py` での読み込み

```python
# apps_py/run_pipeline.py
from cepf_sdk import UnifiedSenseCloud

def main():
    # JSON から USC を初期化
    # 設定は環境ごとに sensors.json を用意する
    usc = UnifiedSenseCloud.from_json("sensors.json")
    
    # あとは通常通り使用
    for sensor_id in ["lidar_north", "lidar_south"]:
        parser = usc.get_parser(sensor_id)
        # パーサーを使用...

if __name__ == "__main__":
    main()
```

---

## 3. アーキテクチャ設計方針

### 3.1 USC とパーサーの関係

**パーサー** = 特定センサの生バイト列を解読する **職人**
**USC** = 職人たちを束ねて仕事を振り分ける **マネージャー**

```
                UnifiedSenseCloud（USC）
               ┌──────────────────────────┐
               │  "どのセンサ？" を判断して │
生データ ──→   │   適切なパーサーに振る     │  ──→  CepfFrame
               │                          │
               │  ┌────────────────────┐   │
               │  │ AiryParser         │   │  ← パーサー A
               │  │ (Airy のバイナリ    │   │
               │  │  解析ができる)      │   │
               │  ├────────────────────┤   │
               │  │ OusterParser       │   │  ← パーサー B
               │  │ (Ouster のバイナリ  │   │
               │  │  解析ができる)      │   │
               │  ├────────────────────┤   │
               │  │ TIRadarParser      │   │  ← パーサー C
               │  │ (TI Radar の解析)   │   │
               │  └────────────────────┘   │
               │                          │
               │  + フィルタ適用           │
               │  + 座標変換              │
               │  + 設置情報付与          │
               └──────────────────────────┘
```

### 3.2 責任範囲の比較表

| 仕事 | パーサー | USC |
|------|:--------:|:---:|
| バイナリのバイト位置を知る | ○ | × |
| 距離・角度の計算式 | ○ | × |
| 強度の正規化 | ○ | × |
| `CepfFrame` の生成 | ○ | × |
| 複数センサの管理 | × | ○ |
| パーサーの登録・検索 | × | ○ |
| 座標変換（sensor→world） | × | ○ |
| フィルタの適用 | × | ○ |
| 複数センサの統合（merge） | × | ○ |
| 設置情報の付与 | × | ○ |

### 3.3 データフロー（パイプライン全体図）

```
RoboSense Airy / Ouster / Radar ...
        │
        │  UDP パケット（生バイト列）
        ▼
┌──────────────────────────────┐
│  トランスポート層（apps/ 側）  │
│  Airy:   socket.recvfrom()   │
│  Ouster: open_source() が担当│
└──────────────┬───────────────┘
               │  raw_bytes (Airy) / LidarScan (Ouster)
               ▼
┌──────────────────────────────┐
│  ドライバー層                 │
│  Airy:   drivers/airy_driver │ ← 自前パケットデコード
│  Ouster: ouster-sdk          │ ← 外部 SDK (XYZLut)
└──────────────┬───────────────┘
               │  AiryPacketData / ndarray
               ▼
┌──────────────────────────────┐
│  UnifiedSenseCloud.forge()   │
│  ┌────────────────────────┐  │
│  │ ① パーサー特定          │  │  sensor_id → parser
│  │ ② validate()           │  │  パケット検証
│  │ ③ parse()              │  │  バイナリ解析 → CepfFrame
│  │ ④ installation 付与    │  │  設置情報（設定時）
│  │ ⑤ Transform 適用       │  │  座標系変換（設定時）
│  │ ⑥ Filters 適用         │  │  フィルタチェーン（設定時）
│  └────────────────────────┘  │
└──────────────┬───────────────┘
               │  CepfFrame
               ▼
┌──────────────────────────────┐
│  アプリケーション処理          │
│  （可視化、保存、検出 etc.）   │
└──────────────────────────────┘
```

### 3.4 Ouster パーサーのデータフロー（ouster-sdk 埋め込み）

Ouster センサの場合、公式 `ouster-sdk` パッケージがパケットデコード・座標変換を担当するため、
CEPF パーサーは **ouster-sdk の薄いラッパー** として実装する。
Airy パーサーのようにバイト列を直接解析する必要はない。

```
【Airy パーサー（従来方式）】

  UDP パケット (1248 bytes)
        │
        ▼
  RoboSenseAiryParser.parse(raw_bytes)
        │  自前でバイナリ解析 + 座標変換
        ▼
  CepfFrame


【Ouster パーサー（ouster-sdk ラッパー方式）】

  Ouster センサ / PCAP ファイル
        │
        ▼
  ouster.sdk.open_source()           ← ouster-sdk がパケット受信・デコード
        │  LidarScan オブジェクト
        ▼
  OusterLidarParser.parse(scan)      ← CEPF パーサーは LidarScan を受け取る
        │
        ├── XYZLut(sensor_info)(scan)  → (H,W,3) XYZ 座標
        ├── scan.field(REFLECTIVITY)   → intensity（/ 65535 で正規化）
        ├── scan.field(SIGNAL)         → signal
        ├── scan.field(NEAR_IR)        → ambient
        ├── confidence 計算            → signal / max(noise, 1) / 100
        ▼
  CepfFrame
```

**ポイント**:
- Ouster パーサーの `parse()` は `bytes` ではなく `ouster.sdk.client.LidarScan` を受け取る
- `RawDataParser` 基底クラスの `parse(raw_data: bytes)` に対し、Ouster では `parse(scan: LidarScan)` とする（型を柔軟にするか、別途 `parse_scan()` メソッドを設ける）
- ouster-sdk は optional dependency（`pip install cepf-sdk[ouster]`）とし、未インストール時は `ImportError` で明確にガイドする

#### 3.4.1 ouster-sdk の主要 API（CEPF パーサーが使用するもの）

| API | モジュール | 説明 |
|-----|----------|------|
| `open_source(url)` | `ouster.sdk` | ライブセンサまたは PCAP を開く。`url` はホスト名 or ファイルパス |
| `SensorInfo` | `ouster.sdk.core` | センサメタデータ（prod_line, beam_angles, format 等） |
| `XYZLut(info)` | `ouster.sdk.core` | SensorInfo から XYZ ルックアップテーブルを生成 |
| `xyz_lut(scan)` | - | LidarScan → `(H, W, 3)` ndarray の座標変換 |
| `LidarScan` | `ouster.sdk.client` | 1 フレーム分のスキャンデータ。フィールド（RANGE, REFLECTIVITY, SIGNAL 等）を持つ |

#### 3.4.2 Airy vs Ouster の設計上の違い

| 観点 | Airy パーサー | Ouster パーサー |
|------|-------------|----------------|
| バイナリ解析 | **自前実装**（struct.unpack 等） | **ouster-sdk に委譲** |
| 座標変換 | 自前 cos/sin 計算 | `XYZLut` が LUT ベースで高速変換 |
| 入力データ型 | `bytes`（UDP パケット） | `LidarScan`（ouster-sdk オブジェクト） |
| フレーム集約 | アプリ層で agg_seconds 管理 | ouster-sdk が 1 回転分を LidarScan で提供 |
| 依存パッケージ | なし（numpy のみ） | `ouster-sdk>=0.13` |
| インストール | `pip install cepf-sdk` | `pip install cepf-sdk[ouster]` |

---

## 4. USC（UnifiedSenseCloud）ファクトリークラスの設計

### 4.1 概要

USC は「翻訳事務所」のような存在。各センサの生データを受け取り、適切なパーサーに解読を依頼し、統一フォーマット（CepfFrame）として返す。

### 4.2 3 つのステップ

#### ステップ 1: パーサーの登録（事前準備）

```python
# SDK に最初から登録されている対応表
_parser_registry = {
    "robosense_airy":  RoboSenseAiryParser,
    "ouster_dome128":  OusterDome128Parser,
    "ouster":          OusterLidarParser,
    "velodyne":        VelodyneLidarParser,
    "ti_radar":        TIRadarParser,
    "continental":     ContinentalRadarParser,
}

# 自作センサに対応させたい場合
UnifiedSenseCloud.register_parser("my_sensor", MySensorParser)
```

#### ステップ 2: 設定ファイルから初期化（推奨）

**JSON 設定ファイル (apps_py/sensors.json):**

```json
{
  "sensors": [
    {
      "sensor_id": "lidar_north",
      "parser_name": "robosense_airy",
      "config": {
        "sensor_type": "LIDAR",
        "model": "RoboSense Airy",
        "num_channels": 32,
        "max_range_m": 200.0
      },
      "transform": {
        "translation": [1.0, 0.0, 0.5],
        "rotation_quaternion": [0.707, 0.0, 0.707, 0.0]
      }
    }
  ],
  "installation": {
    "reference_description": "ビル屋上東側",
    "reference_latitude": 35.6762,
    "reference_longitude": 139.6503,
    "reference_altitude": 220.5
  }
}
```

**Python コード側（apps_py/run_pipeline.py）:**

```python
from cepf_sdk import UnifiedSenseCloud

# JSON から初期化 — プログラマーが SDK 内部を変更せず、設定ファイルだけ管理
usc = UnifiedSenseCloud.from_json("sensors.json")
```

#### ステップ 2 の代替: Python コードで直接指定（テスト時など）

```python
usc = UnifiedSenseCloud()

usc.add_sensor(
    sensor_id="lidar_north",
    parser_name="robosense_airy",
    config=SensorConfig(sensor_type=SensorType.LIDAR, model="RoboSense Airy"),
)

usc.add_sensor(
    sensor_id="radar_front",
    parser_name="ti_radar",
    config=SensorConfig(sensor_type=SensorType.RADAR, model="AWR1843"),
)
```

#### ステップ 3: forge（変換の実行）

```python
frame = usc.forge("lidar_north", raw_udp_bytes)
# → CepfFrame が返る。どのセンサでも同じ呼び方。
```

### 4.3 forge() の内部処理フロー

```
forge("lidar_north", raw_bytes)
  │
  ▼
① sensor_id → パーサーを特定
  │   "lidar_north" → RoboSenseAiryParser
  ▼
② validate(raw_bytes)
  │   パケットが壊れていないか検証
  │   NG → ParseError 例外
  ▼
③ parse(raw_bytes, coordinate_mode)
  │   バイナリ解析 → 座標変換 → 正規化
  │   → CepfFrame を生成
  ▼
④ installation 情報を付与（設定されていれば）
  ▼
⑤ 座標変換 Transform を適用（設定されていれば）
  │   例: sensor_local → world_enu 変換
  ▼
⑥ フィルターを順次適用（登録されていれば）
  │   例: 地面除去、距離制限、ノイズ除去
  ▼
⑦ CepfFrame を返却
```

### 4.4 forge_multi() — 複数センサの統合

```python
frame = usc.forge_multi({
    "lidar_north": lidar_raw_bytes,
    "radar_front": radar_raw_bytes,
})
# → LiDAR + Radar の点群が 1 つの CepfFrame にマージされる
```

### 4.5 USC クラスの属性・メソッド一覧

#### クラス属性

| 属性 | 型 | 説明 |
|------|-----|------|
| `_parser_registry` | `dict[str, type]` | 登録済みパーサークラス辞書 |

#### インスタンス属性

| 属性 | 型 | 説明 |
|------|-----|------|
| `_parsers` | `dict[str, RawDataParser]` | sensor_id → パーサーインスタンス |
| `_transform` | `Transform` | 出力座標変換 |
| `_filters` | `list[Callable]` | 後処理フィルター関数リスト |
| `_output_coordinate` | `CoordinateSystem` | 出力座標系 |
| `_output_coordinate_mode` | `CoordinateMode` | 出力座標表現形式 |
| `_installation` | `InstallationInfo \| None` | 設置情報 |

#### クラスメソッド

| メソッド | 引数 | 戻り値 | 説明 |
|---------|------|--------|------|
| `register_parser(name, parser_class)` | str, type | None | カスタムパーサーを登録 |

#### インスタンスメソッド

| メソッド | 引数 | 戻り値 | 説明 |
|---------|------|--------|------|
| `add_sensor(sensor_id, parser_name, config)` | str, str, SensorConfig | self | センサー追加 |
| `set_transform(translation, rotation_quat)` | list[3], list[4] | self | 座標変換設定 |
| `set_output_coordinate(coord_sys)` | CoordinateSystem | self | 出力座標系設定 |
| `set_output_coordinate_mode(coord_mode)` | CoordinateMode | self | 出力座標表現形式設定 |
| `set_installation(installation)` | InstallationInfo | self | 設置情報設定 |
| `add_filter(filter_func)` | Callable | self | フィルター追加 |
| `forge(sensor_id, raw_data, coordinate_mode=None)` | str, bytes, CoordinateMode \| None | CepfFrame | 単一センサー変換 |
| `forge_multi(data_dict, coordinate_mode=None)` | dict[str, bytes], CoordinateMode \| None | CepfFrame | 複数センサー統合変換 |
| `get_parser(sensor_id)` | str | RawDataParser \| None | パーサー取得 |

### 4.6 現在のコードとの対比

| 仕様（USC 設計） | 現在のコード | 差分 |
|-----------------|-------------|------|
| `UnifiedSenseCloud` | **なし** | ファクトリーが存在しない |
| `usc.forge(id, data)` | `decoder.frames()` | Airy 専用イテレータが UDP 管理まで担当 |
| `RawDataParser.parse(bytes)` | `_decode_packet_cols(pkt)` | 抽象インターフェースなし |
| パーサー登録 | **なし** | センサ切り替え不可 |

**現在:**

```python
decoder = UdpAiryDecoder(config)
for frame in decoder.frames():   # Airy 専用、UDP ソケットも内蔵
    process(frame)
```

**USC 化後:**

```python
usc = UnifiedSenseCloud()
usc.add_sensor("lidar_1", "robosense_airy", config)
usc.add_sensor("lidar_2", "ouster_dome128", config2)  # ouster-sdk が内部で動作

frame = usc.forge("lidar_1", raw_bytes)   # どのセンサでも同じ呼び方

# Ouster の場合は parse_scan() を使用
parser = usc.get_parser("lidar_2")
source = parser.open_source_iter()  # ouster-sdk の open_source() ラッパー
for scan in source:
    frame = parser.parse_scan(scan)
```

### 4.7 USC 化が必要な理由

1. **センサ交換が容易** — LiDAR をメーカーごと変えても `forge()` の呼び出し方は同じ
2. **複数センサ統合** — `forge_multi()` で異種センサの点群を 1 フレームにマージ
3. **後段処理の再利用** — フィルタ・座標変換・保存など、センサ非依存のコードが 1 つで済む
4. **新センサ追加が `register_parser()` 1 行** — 既存コードへの影響ゼロ

---

## 5. パーサー設計

### 5.1 抽象基底クラス: `RawDataParser`

```python
# cepf_sdk/parsers/base.py
from abc import ABC, abstractmethod
from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode
from cepf_sdk.frame import CepfFrame


class RawDataParser(ABC):
    """RAW データパーサーの基底クラス。全パーサーはこれを継承する。"""

    def __init__(self, config: SensorConfig):
        self.config = config
        self._frame_id_counter = 0
        self._default_coordinate_mode = CoordinateMode.CARTESIAN

    def _next_frame_id(self) -> int:
        self._frame_id_counter += 1
        return self._frame_id_counter

    def set_default_coordinate_mode(self, mode: CoordinateMode) -> "RawDataParser":
        self._default_coordinate_mode = mode
        return self

    @abstractmethod
    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """RAW データをパースして CepfFrame を返す。"""
        ...

    @abstractmethod
    def validate(self, raw_data: bytes) -> bool:
        """データの妥当性を検証する。"""
        ...
```

### 5.2 仕様書に定義されたパーサー一覧

| メーカー | 型番 | 種別 | パーサー名 | ファイル | 備考 |
|---------|------|------|-----------|---------|------|
| RoboSense | Airy | LiDAR | `robosense_airy` | `robosense_airy.py` | `drivers/` の自前ドライバーを呼ぶ |
| Ouster | Dome 128 | LiDAR | `ouster_dome128` | `ouster_dome128.py` | `ouster-sdk` ラッパー。`XYZLut` で座標変換 |
| Ouster | OS0/OS1/OS2 | LiDAR | `ouster` | `ouster.py` | `ouster-sdk` ラッパー。Dome 128 と共通基底 |
| Velodyne | VLP/HDL | LiDAR | `velodyne` | `velodyne.py` | 将来 |
| Texas Instruments | AWR/IWR | Radar | `ti_radar` | `ti_radar.py` | 将来 |
| Continental | ARS | Radar | `continental` | `continental.py` | 将来 |

### 5.3 パーサーの coordinate_mode 対応

| coordinate_mode | パース動作 |
|-----------------|-----------|
| CARTESIAN | 極座標→直交座標変換を実行、x/y/z のみ格納 |
| SPHERICAL | 座標変換なし、azimuth/elevation/range のみ格納 |
| BOTH | 極座標を保持しつつ直交座標変換も実行、全フィールド格納 |
| CARTESIAN_WITH_RANGE | 極座標→直交座標変換を実行、x/y/z/range を格納 |

### 5.4 Airy パーサーの 3 層設計

現在の `airy/decoder.py` は 1 ファイルに全てが詰まっている。
これを Ouster と対称的な構造に分離する。

#### 5.4.1 Ouster との対比

```
【Ouster のレイヤー構造】

  ouster-sdk（外部パッケージ from PyPI）
  ├── パケットデコード    ← ouster-sdk 内部
  ├── LidarScan 生成     ← ouster-sdk 内部
  └── XYZLut 座標変換    ← ouster-sdk 内部
           ↓ LidarScan
  parsers/ouster.py      ← 薄いラッパー
           ↓ CepfFrame


【Airy のレイヤー構造（リファクタリング後）】

  drivers/robosense_airy_driver.py（自前実装 ≒ Airy の "SDK" に相当）
  ├── パケットデコード    ← _decode_packet_cols() を移植
  ├── 定数群              ← PKT_LEN, HDR, DB_SIZE etc.
  └── 角度テーブル        ← vert_deg → ラジアン変換
           ↓ AiryPacketData (dict or dataclass)
  parsers/robosense_airy.py  ← 座標変換 + CepfFrame 生成
           ↓ CepfFrame
```

つまり `drivers/robosense_airy_driver.py` は **自前の Airy SDK** であり、
Ouster における `ouster-sdk` パッケージと同じ役割を果たす。

#### 5.4.2 各層の責任分担（Airy）

| 層 | ファイル | 何をするか | 何をしないか |
|---|---------|-----------|------------|
| **トランスポート** | `apps/` 側 | UDP `socket.bind()` / `recvfrom()` | バイナリ解析 |
| **ドライバー** | `drivers/robosense_airy_driver.py` | パケットのバイナリ解析（距離・角度・強度値の抽出） | 座標変換、CepfFrame 生成 |
| **パーサー** | `parsers/robosense_airy.py` | ドライバー出力 → 座標変換 → CepfFrame 生成 | バイナリ解析、UDP |
| **フレーム集約** | `apps/` または USC | `agg_seconds` 時間窓で複数パケットをバッファリング | パケット解析 |

#### 5.4.3 `drivers/robosense_airy_driver.py` の設計

```python
# cepf_sdk/drivers/robosense_airy_driver.py
"""
RoboSense Airy パケットデコーダー（ドライバー層）。

公式 SDK が提供されていない RoboSense Airy の生 UDP パケットを
デコードするための自前実装。Ouster における ouster-sdk と同じ役割。

責任:
  - 1248 バイトの UDP パケットをデコードし、各チャンネルの距離・角度・強度を返す
  - CepfFrame は知らない（パーサー層の仕事）
  - UDP ソケットは管理しない（apps/ 層の仕事）
"""
from dataclasses import dataclass
import numpy as np

# ---- パケット定数（現 decoder.py から移植） ----
PKT_LEN = 1248       # 1 パケットのバイト数
HDR = 42             # ヘッダ長
DB_SIZE = 148        # 1 Data Block のサイズ
N_DB = 8             # 1 パケット内の Data Block 数
CH_PER_DB = 48       # 1 Data Block 内のチャンネル数（上位 + 下位）
DIST_MASK = 0x3FFF   # 14bit 距離値のマスク
FLAG_EXPECT = 0xFFEE # 有効な Data Block のフラグ値
TICK_OFF = 26        # タイムスタンプのバイトオフセット


@dataclass
class AiryPacketData:
    """1 パケット分のデコード結果。CepfFrame とは無関係。"""
    azimuth_rad: np.ndarray       # (N_cols,) 各列の方位角 [rad]
    elevation_rad: np.ndarray     # (N_channels,) 各チャンネルの仰角 [rad]
    distance_m: np.ndarray        # (N_channels, N_cols) 距離 [m]
    intensity_raw: np.ndarray     # (N_channels, N_cols) 生強度値
    timestamp_us: int             # パケットタイムスタンプ [μs]
    valid_mask: np.ndarray        # (N_channels, N_cols) 有効フラグ


@dataclass
class AiryDriverConfig:
    """ドライバー設定。現 AiryDecodeConfig のうちバイナリ解析に関する部分のみ。"""
    vert_deg: tuple[float, ...] = (...)  # 96ch の仰角テーブル
    dist_scale_m: float = 0.002
    intensity_div: float = 255.0


def decode_packet(pkt: bytes, config: AiryDriverConfig) -> AiryPacketData | None:
    """
    1248 バイトの Airy パケットをデコードする。
    現在の decoder.py._decode_packet_cols() から移植。

    Parameters
    ----------
    pkt : bytes
        受信した生パケット（len == 1248）
    config : AiryDriverConfig
        デコード設定

    Returns
    -------
    AiryPacketData | None
        無効なパケットの場合は None
    """
    if len(pkt) != PKT_LEN:
        return None
    # ... 現在の _decode_packet_cols() のロジックをここに移植 ...


def validate_packet(pkt: bytes) -> bool:
    """パケットの基本的な妥当性を検証する。"""
    return len(pkt) == PKT_LEN  # + FLAG_EXPECT チェック等
```

#### 5.4.4 `parsers/robosense_airy.py` の設計

```python
# cepf_sdk/parsers/robosense_airy.py
"""
RoboSense Airy パーサー。
ドライバー層 (drivers/robosense_airy_driver.py) の出力を CepfFrame に変換する。
"""
import numpy as np
from cepf_sdk.config import SensorConfig
from cepf_sdk.drivers.robosense_airy_driver import (
    AiryDriverConfig, AiryPacketData, decode_packet, validate_packet,
)
from cepf_sdk.enums import CoordinateMode
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints


class RoboSenseAiryParser(RawDataParser):
    """
    RoboSense Airy パーサー。
    
    Ouster パーサーとの対比:
    - Ouster: ouster-sdk (外部) → parse_scan(LidarScan) → CepfFrame
    - Airy:   drivers/ (自前)   → parse(bytes) → CepfFrame
    """

    def __init__(self, config: SensorConfig,
                 driver_config: AiryDriverConfig | None = None):
        super().__init__(config)
        self._driver_config = driver_config or AiryDriverConfig()

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        1 パケット (1248 bytes) をパースして CepfFrame を返す。
        
        内部で drivers/robosense_airy_driver.decode_packet() を呼ぶ。
        """
        pkt_data = decode_packet(raw_data, self._driver_config)
        if pkt_data is None:
            raise ParseError("無効な Airy パケット")

        mode = coordinate_mode or self._default_coordinate_mode
        points = self._convert_to_points(pkt_data, mode)

        return CepfFrame(
            format="CEPF",
            version="1.2.0",
            metadata=self._build_metadata(pkt_data, mode),
            schema=list(points.keys()),
            points=points,
            point_count=len(points["x"]),
        )

    def _convert_to_points(self, pkt: AiryPacketData,
                           mode: CoordinateMode) -> CepfPoints:
        """AiryPacketData → 座標変換 → CepfPoints"""
        # 極座標 → 直交座標変換（現 decoder.py のロジック）
        ...

    def validate(self, raw_data: bytes) -> bool:
        return validate_packet(raw_data)
```

#### 5.4.5 レイヤー対称性のまとめ

| レイヤー | Airy（自前実装） | Ouster（外部 SDK） |
|---------|-----------------|-------------------|
| **ドライバー** | `drivers/robosense_airy_driver.py` | `ouster-sdk` (PyPI) |
| **入力** | `bytes` (1248B UDP パケット) | `LidarScan` (ouster-sdk オブジェクト) |
| **デコード関数** | `decode_packet(pkt, config)` | `XYZLut(info)(scan)` |
| **中間データ型** | `AiryPacketData` (自前 dataclass) | `LidarScan` (ouster-sdk クラス) |
| **パーサー** | `parsers/robosense_airy.py` | `parsers/ouster.py` |
| **パーサーメソッド** | `parse(raw_bytes)` | `parse_scan(scan)` |
| **出力** | `CepfFrame` | `CepfFrame` |
| **フレーム集約** | `apps/` 層で agg_seconds 管理 | ouster-sdk が LidarScan 単位で提供 |
| **インストール** | `pip install cepf-sdk` (追加不要) | `pip install cepf-sdk[ouster]` |

### 5.5 後方互換の維持

既存の `apps/run_pipeline.py` が `from cepf_sdk.airy import UdpAiryDecoder, AiryDecodeConfig` をインポートしているため、`airy/` は後方互換ラッパーとして残す：

```python
# cepf_sdk/airy/__init__.py（後方互換ラッパー）
import warnings
warnings.warn(
    "cepf_sdk.airy is deprecated. Use cepf_sdk.parsers and cepf_sdk.usc instead.",
    DeprecationWarning, stacklevel=2,
)
from .decoder import UdpAiryDecoder, AiryDecodeConfig
__all__ = ["UdpAiryDecoder", "AiryDecodeConfig"]
```

### 5.6 Ouster パーサー設計（ouster-sdk 埋め込み）

#### 5.6.1 設計方針

Ouster パーサーは、公式 `ouster-sdk` パッケージを **内部依存** として使用する。
Airy パーサーとは異なり、バイト列の直接解析は行わない。

```
Airy:   raw_bytes → [自前バイナリ解析] → CepfFrame
Ouster: LidarScan → [ouster-sdk API 呼び出し] → CepfFrame
```

**理由**:
- Ouster のパケットフォーマットはセンサ世代・解像度モードによって異なり、自前実装は非現実的
- ouster-sdk が `XYZLut` による高速 LUT ベース座標変換を提供（自前 cos/sin よりも高速・高精度）
- ouster-sdk が LidarScan（1 回転分のフレーム集約）を自動で行うため、フレーム管理不要

#### 5.6.2 クラス階層

```
RawDataParser (ABC)
    │
    ├── RoboSenseAiryParser       ← drivers/airy_driver を呼ぶ（自前ドライバー）
    │       └── 内部で decode_packet() → AiryPacketData → CepfFrame
    │
    └── OusterBaseParser (ABC)    ← ouster-sdk を呼ぶ（外部ドライバー）
            │   └── 内部で XYZLut(scan) → ndarray → CepfFrame
            │
            ├── OusterDome128Parser    ← Dome 128 固有設定
            └── OusterLidarParser      ← OS0/OS1/OS2 汎用


ドライバー層（パーサーが内部的に使う）:
    ┌────────────────────────────────────────────┐
    │ drivers/robosense_airy_driver.py (自前)     │ ←  Airy パーサーが使う
    │   decode_packet(bytes) → AiryPacketData    │
    ├────────────────────────────────────────────┤
    │ ouster-sdk (PyPI 外部パッケージ)            │ ←  Ouster パーサーが使う
    │   XYZLut(info)(scan) → ndarray             │
    └────────────────────────────────────────────┘
```

#### 5.6.3 `OusterBaseParser` — Ouster 共通基底クラス

```python
# cepf_sdk/parsers/ouster.py
"""
Ouster LiDAR 共通パーサー基底クラス。
ouster-sdk (pip install ouster-sdk) を内部依存として使用する。

インストール:
    pip install cepf-sdk[ouster]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np

from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, SensorType
from cepf_sdk.errors import ConfigurationError, ParseError
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.types import CepfPoints

# --- ouster-sdk の遅延インポート（optional dependency） ---
try:
    from ouster.sdk import open_source
    from ouster.sdk.core import SensorInfo, XYZLut
    _HAS_OUSTER = True
except ImportError:
    _HAS_OUSTER = False


def _require_ouster() -> None:
    """ouster-sdk が未インストールの場合に明確なエラーを出す。"""
    if not _HAS_OUSTER:
        raise ImportError(
            "ouster-sdk が必要です。以下のコマンドでインストールしてください:\n"
            "  pip install cepf-sdk[ouster]\n"
            "または:\n"
            "  pip install ouster-sdk"
        )


@dataclass
class OusterConfig:
    """Ouster センサ固有の設定。SensorConfig と併用。"""
    source_url: str = ""
    """ライブセンサのホスト名、または PCAP ファイルパス"""
    meta_json: str = ""
    """PCAP 再生時のメタデータ JSON ファイルパス（ライブ時は空）"""
    collate: bool = True
    """PCAP 再生時の collate オプション（デフォルト True）"""


class OusterBaseParser(RawDataParser):
    """
    Ouster LiDAR 共通パーサー。
    ouster-sdk の LidarScan を受け取り CepfFrame に変換する。

    通常の RawDataParser.parse(bytes) とは異なり、
    parse_scan(scan) メソッドで LidarScan を直接受け渡す。
    """

    def __init__(self, config: SensorConfig, ouster_config: OusterConfig | None = None):
        _require_ouster()
        super().__init__(config)
        self._ouster_config = ouster_config or OusterConfig()
        self._sensor_info: SensorInfo | None = None
        self._xyz_lut: Any = None  # XYZLut インスタンス

    def set_sensor_info(self, info: SensorInfo) -> None:
        """SensorInfo を設定し、XYZLut を初期化する。"""
        self._sensor_info = info
        self._xyz_lut = XYZLut(info)

    @property
    def sensor_info(self) -> SensorInfo | None:
        return self._sensor_info

    @property
    def model_name(self) -> str:
        """センサモデル名（例: 'Dome-128-Rev-D'）"""
        if self._sensor_info:
            return self._sensor_info.prod_line
        return self.config.model

    @property
    def columns_per_frame(self) -> int:
        """1 フレームあたりの列数"""
        if self._sensor_info:
            return self._sensor_info.format.columns_per_frame
        return 0

    @property
    def pixels_per_column(self) -> int:
        """1 列あたりのピクセル数（= チャンネル数）"""
        if self._sensor_info:
            return self._sensor_info.format.pixels_per_column
        return 0

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        bytes インターフェース（基底クラスの互換性のため）。
        Ouster では通常 parse_scan() を使用する。
        raw_data は無視される。
        """
        raise NotImplementedError(
            "Ouster パーサーは parse_scan(scan) を使用してください。"
            "ouster-sdk の open_source() で取得した LidarScan を渡してください。"
        )

    def parse_scan(self, scan: Any,
                   coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        """
        ouster.sdk.client.LidarScan を CepfFrame に変換する。

        Parameters
        ----------
        scan : ouster.sdk.client.LidarScan
            1 フレーム分の LiDAR スキャンデータ
        coordinate_mode : CoordinateMode | None
            座標モード。None の場合はデフォルト値を使用

        Returns
        -------
        CepfFrame
        """
        if self._xyz_lut is None:
            raise ConfigurationError(
                "SensorInfo が未設定です。set_sensor_info() を先に呼んでください。"
            )

        mode = coordinate_mode or self._default_coordinate_mode

        # ---- XYZ 座標の取得 ----
        xyz = self._xyz_lut(scan)                    # (H, W, 3) ndarray
        xyz_flat = xyz.reshape(-1, 3)                # (N, 3)
        x = xyz_flat[:, 0].astype(np.float32)
        y = xyz_flat[:, 1].astype(np.float32)
        z = xyz_flat[:, 2].astype(np.float32)

        # ---- 距離 ----
        range_field = scan.field(self._range_field_id())
        range_m = range_field.reshape(-1).astype(np.float32) * 0.001  # mm → m

        # ---- 強度（反射率） ----
        reflectivity = scan.field(self._reflectivity_field_id())
        intensity = reflectivity.reshape(-1).astype(np.float32) / 65535.0

        # ---- 信号強度とノイズ → 信頼度 ----
        signal_arr = self._safe_field(scan, self._signal_field_id())
        noise_arr = self._safe_field(scan, self._near_ir_field_id())

        if signal_arr is not None and noise_arr is not None:
            sig = signal_arr.reshape(-1).astype(np.float32)
            noi = noise_arr.reshape(-1).astype(np.float32)
            confidence = np.clip(sig / np.maximum(noi, 1.0) / 100.0, 0.0, 1.0)
        else:
            confidence = np.ones_like(x)

        # ---- CepfPoints の構築 ----
        points: CepfPoints = {}
        if mode in (CoordinateMode.CARTESIAN, CoordinateMode.BOTH,
                    CoordinateMode.CARTESIAN_WITH_RANGE):
            points["x"] = x
            points["y"] = y
            points["z"] = z
        if mode in (CoordinateMode.SPHERICAL, CoordinateMode.BOTH):
            points["azimuth"] = np.arctan2(y, x).astype(np.float32)
            points["elevation"] = np.arctan2(
                z, np.sqrt(x**2 + y**2)
            ).astype(np.float32)
            points["range"] = range_m
        if mode == CoordinateMode.CARTESIAN_WITH_RANGE:
            points["range"] = range_m
        points["intensity"] = intensity
        points["confidence"] = confidence

        # ---- メタデータ ----
        frame_id = self._next_frame_id()
        metadata = CepfMetadata(
            timestamp_utc=0.0,   # TODO: scan.timestamp から変換
            frame_id=frame_id,
            coordinate_system="sensor_local",
            coordinate_mode=mode.value if isinstance(mode, CoordinateMode) else str(mode),
            units={"distance": "m", "angle": "rad", "intensity": "normalized"},
            sensor=self.model_name,
        )

        return CepfFrame(
            format="CEPF",
            version="1.2.0",
            metadata=metadata,
            schema=list(points.keys()),
            points=points,
            point_count=len(x),
        )

    # --- 抽象フィールド ID（サブクラスでオーバーライド可） ---

    def _range_field_id(self) -> int:
        """RANGE フィールドの ID。ouster.sdk.client.ChanField.RANGE"""
        try:
            from ouster.sdk.client import ChanField
            return ChanField.RANGE
        except ImportError:
            return 1  # fallback

    def _reflectivity_field_id(self) -> int:
        try:
            from ouster.sdk.client import ChanField
            return ChanField.REFLECTIVITY
        except ImportError:
            return 3

    def _signal_field_id(self) -> int:
        try:
            from ouster.sdk.client import ChanField
            return ChanField.SIGNAL
        except ImportError:
            return 2

    def _near_ir_field_id(self) -> int:
        try:
            from ouster.sdk.client import ChanField
            return ChanField.NEAR_IR
        except ImportError:
            return 4

    def _safe_field(self, scan: Any, field_id: int) -> np.ndarray | None:
        """フィールドが存在しない場合は None を返す。"""
        try:
            return scan.field(field_id)
        except (ValueError, KeyError):
            return None

    def validate(self, raw_data: bytes) -> bool:
        """Ouster では ouster-sdk がバリデーションを行うため常に True。"""
        return True

    # --- ユーティリティ: open_source ヘルパー ---

    def open_source_iter(self) -> Iterator[Any]:
        """
        OusterConfig の設定に基づき ouster.sdk.open_source() を開き、
        LidarScan のイテレータを返す。

        Returns
        -------
        Iterator[LidarScan]

        使用例::

            parser = OusterLidarParser(config, ouster_config)
            source = parser.open_source_iter()
            # source.sensor_info[0] から SensorInfo を取得
            for scan in source:
                frame = parser.parse_scan(scan)
        """
        _require_ouster()
        cfg = self._ouster_config
        if cfg.meta_json:
            # PCAP 再生モード
            src = open_source(cfg.source_url, meta=[cfg.meta_json],
                              collate=cfg.collate)
        else:
            # ライブセンサモード
            src = open_source(cfg.source_url)

        # SensorInfo を自動設定
        if hasattr(src, 'sensor_info') and src.sensor_info:
            info = src.sensor_info[0] if isinstance(src.sensor_info, list) else src.sensor_info
            self.set_sensor_info(info)

        return src
```

#### 5.6.4 `OusterDome128Parser` — Dome 128 固有パーサー

```python
# cepf_sdk/parsers/ouster_dome128.py
"""Ouster Dome 128 用パーサー。"""
from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import SensorType
from cepf_sdk.parsers.ouster import OusterBaseParser, OusterConfig


class OusterDome128Parser(OusterBaseParser):
    """
    Ouster Dome 128 半天球 LiDAR パーサー。

    Dome 128 固有の特徴:
    - 128ch × 1024/2048 列
    - 半天球 FoV（上方 90°）
    - Dome 専用のビームパターン
    """

    def __init__(self, config: SensorConfig | None = None,
                 ouster_config: OusterConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.LIDAR,
                model="Ouster Dome 128",
                num_channels=128,
                horizontal_fov_deg=360.0,
                vertical_fov_deg=90.0,
                max_range_m=100.0,
            )
        super().__init__(config, ouster_config)
```

#### 5.6.5 `OusterLidarParser` — OS シリーズ汎用パーサー

```python
# cepf_sdk/parsers/ouster.py に追加（OusterBaseParser の下）
class OusterLidarParser(OusterBaseParser):
    """
    Ouster OS0/OS1/OS2 シリーズ汎用パーサー。

    prod_line 情報は ouster-sdk の SensorInfo から自動取得される。
    """

    def __init__(self, config: SensorConfig | None = None,
                 ouster_config: OusterConfig | None = None):
        if config is None:
            config = SensorConfig(
                sensor_type=SensorType.LIDAR,
                model="Ouster OS",
                num_channels=128,
                horizontal_fov_deg=360.0,
                vertical_fov_deg=45.0,
                max_range_m=240.0,
            )
        super().__init__(config, ouster_config)
```

#### 5.6.6 USC からの Ouster パーサー使用例

```python
from cepf_sdk import UnifiedSenseCloud
from cepf_sdk.config import SensorConfig
from cepf_sdk.enums import SensorType
from cepf_sdk.parsers.ouster import OusterConfig

# ---- ライブセンサ接続 ----
usc = UnifiedSenseCloud()
usc.add_sensor(
    sensor_id="dome_1",
    parser_name="ouster_dome128",
    config=SensorConfig(sensor_type=SensorType.LIDAR, model="Dome 128"),
    ouster_config=OusterConfig(source_url="os-122312345678.local"),
)

# パーサー経由で ouster-sdk のソースを開く
parser = usc.get_parser("dome_1")
source = parser.open_source_iter()  # SensorInfo が自動設定される

for scan in source:
    frame = parser.parse_scan(scan)
    # frame は CepfFrame — 通常のフィルタ・変換がそのまま使える

# ---- PCAP 再生 ----
usc.add_sensor(
    sensor_id="dome_replay",
    parser_name="ouster_dome128",
    config=SensorConfig(sensor_type=SensorType.LIDAR, model="Dome 128"),
    ouster_config=OusterConfig(
        source_url="/path/to/capture.pcap",
        meta_json="/path/to/metadata.json",
        collate=False,
    ),
)
```

#### 5.6.7 ouster-sdk のバージョン互換性

| ouster-sdk バージョン | 対応状況 | 備考 |
|---------------------|---------|------|
| `0.11.x` | △ | `open_source` なし。`pcap.Pcap` + `Scans` を直接使用 |
| `0.12.x` | ○ | `open_source` 導入 |
| `0.13.x` 以降 | ○ (推奨) | 安定版 API |

最低要件: `ouster-sdk>=0.13`。古いバージョンでは `open_source` が存在しないため明示的に弾く。

---

## 6. フィルター設計

### 6.1 設計方針

フィルターは 2 種類の動作に分かれる：

| 種類 | 動作 | 例 |
|------|------|-----|
| **マスクフィルター** | 条件に合わない点を **削除** | 範囲カット、ROR、SOR |
| **フラグフィルター** | 点は残し `flags` に **ラベル付け** | 地面検出、ノイズ検出 |

この 2 つを **同じインターフェース** で扱う。

### 6.2 基底クラス: `PointFilter`

```python
# cepf_sdk/filters/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
import numpy as np
from cepf_sdk.types import CepfPoints


class FilterMode(Enum):
    """フィルターの動作モード"""
    MASK = "mask"      # 点を削除する
    FLAG = "flag"      # flags にビットを立てる（点は残す）


@dataclass
class FilterResult:
    """フィルター適用結果"""
    points: CepfPoints
    mask: Optional[np.ndarray]
    count_before: int
    count_after: int

    @property
    def removed(self) -> int:
        return self.count_before - self.count_after


class PointFilter(ABC):
    """
    全フィルターの基底クラス。
    サブクラスは compute_mask() だけ実装すればよい。
    """

    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    @abstractmethod
    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        """残す点 = True、除去する点 = False の boolean 配列を返す。"""
        ...

    def apply(self, points: CepfPoints) -> FilterResult:
        """共通の適用ロジック（サブクラスはオーバーライド不要）"""
        x = np.asarray(points["x"])
        n_before = len(x)
        mask = self.compute_mask(points)

        if self.mode == FilterMode.MASK:
            out = _apply_mask(points, mask)
            n_after = int(np.count_nonzero(mask))
        else:
            out = dict(points)
            flags = np.asarray(out.get("flags", np.zeros(n_before, dtype=np.uint16)))
            flags = flags.copy()
            flags[~mask] |= self.flag_bit
            out["flags"] = flags
            n_after = n_before

        return FilterResult(points=out, mask=mask,
                            count_before=n_before, count_after=n_after)


def _apply_mask(points: CepfPoints, mask: np.ndarray) -> CepfPoints:
    """mask=True の点だけ残す"""
    n = len(mask)
    out: Dict[str, np.ndarray] = {}
    for k, v in points.items():
        a = np.asarray(v)
        if a.ndim == 1 and len(a) == n:
            out[k] = a[mask]
        else:
            out[k] = a
    return out
```

**設計のポイント**: 新フィルターの開発者は `compute_mask()` だけ書けばよい。削除/フラグ付与の切り替えは基底クラスが自動対応する。

### 6.3 フィルター一覧と実装仕様

#### 6.3.1 領域カット系（`filters/range/`）

| フィルター | ファイル | パラメータ | compute_mask の条件 |
|-----------|---------|-----------|-------------------|
| **CylindricalFilter** | `cylindrical.py` | `radius_m`, `z_min_m`, `z_max_m`, `cx`, `cy`, `invert` | `(r² ≤ radius²) & (z_min ≤ z ≤ z_max)` |
| **SphericalFilter** | `spherical.py` | `radius_m`, `cx`, `cy`, `cz`, `invert` | `(dx² + dy² + dz²) ≤ radius²` |
| **BoxFilter** | `box.py` | `x_min/max`, `y_min/max`, `z_min/max`, `invert` | `(x_min ≤ x ≤ x_max) & ...` |
| **PolygonFilter** | `polygon.py` | `polygon: list[(x,y)]`, `z_min`, `z_max`, `invert` | XY 平面の多角形内判定 × Z 範囲 |

各フィルターの `invert` パラメータ：
- `False`（デフォルト）: 領域 **内側** を残す
- `True`: 領域 **外側** を残す（センサ直近のノイズ除去等に使用）

#### 6.3.2 統計系（`filters/statistical/`）

| フィルター | ファイル | パラメータ | アルゴリズム |
|-----------|---------|-----------|------------|
| **RadiusOutlierRemoval** | `ror.py` | `radius_m`, `min_neighbors` | 半径内の近傍点数が閾値未満なら除去。`scipy.spatial.cKDTree` 使用 |
| **StatisticalOutlierRemoval** | `sor.py` | `k_neighbors`, `std_ratio` | k 近傍の平均距離が `(全体平均 + std_ratio × 標準偏差)` 超で除去 |
| **VoxelDownsample** | `voxel.py` | `voxel_size` | ボクセルグリッド内の最初の点だけ残す |

#### 6.3.3 属性値ベース（`filters/attribute/`）

| フィルター | ファイル | パラメータ | 条件 |
|-----------|---------|-----------|------|
| **IntensityFilter** | `intensity.py` | `min_intensity`, `max_intensity` | 強度の閾値フィルタ |
| **ConfidenceFilter** | `confidence.py` | `min_confidence` | 信頼度の閾値フィルタ |
| **FlagFilter** | `flag.py` | `include_flags`, `exclude_flags` | フラグのビットマスクフィルタ |

#### 6.3.4 分類・ラベリング（`filters/classification/`）

| フィルター | ファイル | パラメータ | 動作 |
|-----------|---------|-----------|------|
| **GroundClassifier** | `ground.py` | `z_threshold` | `flags \|= GROUND` を付与 |
| **NoiseClassifier** | `noise.py` | `neighbors`, `radius` | `flags \|= NOISE` を付与 |

### 6.4 パイプライン（フィルターの連鎖）

```python
# cepf_sdk/filters/pipeline.py
@dataclass
class FilterPipeline:
    """複数フィルターを順番に適用する。"""
    filters: List[PointFilter] = field(default_factory=list)
    verbose: bool = False

    def apply(self, points: CepfPoints) -> FilterResult:
        current = points
        n_original = len(points["x"])
        for f in self.filters:
            result = f.apply(current)
            if self.verbose:
                name = type(f).__name__
                print(f"  [{name}] {result.count_before} → {result.count_after}"
                      f" (removed {result.removed})")
            current = result.points
        n_final = len(current["x"])
        return FilterResult(points=current, mask=None,
                            count_before=n_original, count_after=n_final)
```

### 6.5 フィルター適用順の推奨

```
① 領域カット（計算コスト: 低 → 点数を大幅に削減）
  ↓
② 属性フィルタ（計算コスト: 低 → 強度・信頼度で足切り）
  ↓
③ 統計フィルタ（計算コスト: 高 → 削減済みの点群に対して実行）
  ↓
④ ダウンサンプリング（最後 → 最終的な密度調整）
```

**鉄則**: 計算コストの高い ROR/SOR は、先に安いフィルタで点を減らしてから実行する。

### 6.6 使い方イメージ

```python
from cepf_sdk.filters import (
    FilterPipeline,
    CylindricalFilter,
    SphericalFilter,
    RadiusOutlierRemoval,
    VoxelDownsample,
)
from dataclasses import replace

pipeline = FilterPipeline(
    filters=[
        CylindricalFilter(radius_m=20.0, z_min_m=0.0, z_max_m=15.0),
        SphericalFilter(radius_m=0.5, invert=True),       # 直近ノイズ除去
        RadiusOutlierRemoval(radius_m=0.3, min_neighbors=5),
        VoxelDownsample(voxel_size=0.05),
    ],
    verbose=True,
)

for frame in decoder.frames():
    result = pipeline.apply(frame.points)
    frame = replace(frame, points=result.points, point_count=result.count_after)
```

出力例:
```
  [CylindricalFilter] 51234 → 38921 (removed 12313)
  [SphericalFilter] 38921 → 38845 (removed 76)
  [RadiusOutlierRemoval] 38845 → 36102 (removed 2743)
  [VoxelDownsample] 36102 → 11847 (removed 24255)
```

---

## 7. 実装 TODO（優先順位付き）

### フェーズ 1: 基盤モジュール（他の全モジュールが依存）

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 1-1 | 列挙型の実装 | `cepf_sdk/enums.py` | なし | `SensorType`, `CoordinateSystem`, `CoordinateMode`, `PointFlag` が定義されている |
| 1-2 | 設定クラスの実装 | `cepf_sdk/config.py` | `enums.py` | `SensorConfig`, `Transform`, `InstallationInfo` が定義されている |
| 1-3 | エラー階層の実装 | `cepf_sdk/errors.py` | なし | `CEPFError` → `ParseError` → `InvalidHeaderError` etc. が定義されている |
| 1-4 | `frame.py` の拡張 | `cepf_sdk/frame.py` | `enums.py`, `config.py` | `CepfMetadata` が `CoordinateMode` 等を使用。`to_json()`, `to_numpy()` メソッド追加 |
| 1-5 | `__init__.py` の更新 | `cepf_sdk/__init__.py` | 上記全部 | 新モジュールの公開 API を re-export |

### フェーズ 2: ドライバー・パーサー基盤

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 2-1 | 抽象基底クラス実装 | `cepf_sdk/parsers/base.py` | `config.py`, `enums.py`, `frame.py` | `RawDataParser` ABC が定義され、`parse()` / `validate()` が抽象メソッド |
| 2-2 | Airy ドライバー作成 | `cepf_sdk/drivers/robosense_airy_driver.py` | なし（numpy のみ） | `decode_packet()` が `AiryPacketData` を返す。CepfFrame を知らない。現 `_decode_packet_cols()` のロジックを移植 完了 |
| 2-3 | Airy パーサー実装 | `cepf_sdk/parsers/robosense_airy.py` | `parsers/base.py`, `drivers/` | `RawDataParser` を継承。内部で `decode_packet()` を呼び、座標変換 + CepfFrame 生成 |
| 2-4 | パーサー `__init__.py` | `cepf_sdk/parsers/__init__.py` | 上記 | パーサー登録マップが定義されている |
| 2-5 | `airy/` 後方互換化 | `cepf_sdk/airy/decoder.py` | `parsers/robosense_airy.py` | 既存 import が壊れない（DeprecationWarning 付き） |

### フェーズ 3: USC メインクラス

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 3-1 | USC 実装 | `cepf_sdk/usc.py` | `parsers/`, `config.py`, `enums.py` | `forge()`, `forge_multi()`, `add_sensor()`, `register_parser()` が動作 |
| 3-2 | `__init__.py` に USC 追加 | `cepf_sdk/__init__.py` | `usc.py` | `from cepf_sdk import UnifiedSenseCloud` が可能 |

### フェーズ 4: フィルター

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 4-1 | フィルター基底クラス | `cepf_sdk/filters/base.py` | `types.py` | `PointFilter`, `FilterMode`, `FilterResult` が定義 |
| 4-2 | パイプライン | `cepf_sdk/filters/pipeline.py` | `filters/base.py` | `FilterPipeline` が複数フィルタを連鎖適用 |
| 4-3 | 円筒形フィルタ | `cepf_sdk/filters/range/cylindrical.py` | `filters/base.py` | `CylindricalFilter` が動作 |
| 4-4 | 球形フィルタ | `cepf_sdk/filters/range/spherical.py` | `filters/base.py` | `SphericalFilter` が動作 |
| 4-5 | 直方体フィルタ | `cepf_sdk/filters/range/box.py` | `filters/base.py` | `BoxFilter` が動作 |
| 4-6 | ROR | `cepf_sdk/filters/statistical/ror.py` | `filters/base.py`, `scipy` | `RadiusOutlierRemoval` が動作 |
| 4-7 | SOR | `cepf_sdk/filters/statistical/sor.py` | `filters/base.py`, `scipy` | `StatisticalOutlierRemoval` が動作 |
| 4-8 | ボクセル | `cepf_sdk/filters/statistical/voxel.py` | `filters/base.py` | `VoxelDownsample` が動作 |
| 4-9 | 強度フィルタ | `cepf_sdk/filters/attribute/intensity.py` | `filters/base.py` | `IntensityFilter` が動作 |
| 4-10 | 信頼度フィルタ | `cepf_sdk/filters/attribute/confidence.py` | `filters/base.py` | `ConfidenceFilter` が動作 |
| 4-11 | フラグフィルタ | `cepf_sdk/filters/attribute/flag.py` | `filters/base.py` | `FlagFilter` が動作 |
| 4-12 | 地面検出 | `cepf_sdk/filters/classification/ground.py` | `filters/base.py` | `GroundClassifier` がフラグを付与 |
| 4-13 | ノイズ検出 | `cepf_sdk/filters/classification/noise.py` | `filters/base.py` | `NoiseClassifier` がフラグを付与 |
| 4-14 | フィルター `__init__.py` | `cepf_sdk/filters/__init__.py` | 上記全部 | 全フィルターが re-export されている |

### フェーズ 5: ユーティリティ

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 5-1 | 座標変換 | `cepf_sdk/utils/coordinates.py` | `numpy` | `spherical_to_cartesian`, `cartesian_to_spherical`, `lla_to_ecef`, `ecef_to_lla` |
| 5-2 | クォータニオン | `cepf_sdk/utils/quaternion.py` | `numpy` | `quaternion_to_rotation_matrix`, `rotation_matrix_to_quaternion` |
| 5-3 | I/O | `cepf_sdk/utils/io.py` | `frame.py` | `load_cepf_file`, `save_cepf_file`, `cepf_to_pcd`, `cepf_to_las` |

### フェーズ 6: 追加パーサー

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 6-1 | Ouster 共通基底クラス | `cepf_sdk/parsers/ouster.py` | `parsers/base.py`, `ouster-sdk` | `OusterBaseParser` が `LidarScan` → `CepfFrame` 変換を実行。`XYZLut` で座標変換。`open_source_iter()` でライブ/PCAP 対応 |
| 6-2 | Ouster Dome 128 | `cepf_sdk/parsers/ouster_dome128.py` | `parsers/ouster.py` | `OusterDome128Parser` が Dome 128 固有設定を持ち、ouster-sdk 経由で動作 |
| 6-3 | Ouster OS シリーズ | `cepf_sdk/parsers/ouster.py` | `parsers/ouster.py` | `OusterLidarParser` が OS0/OS1/OS2 に対応。SensorInfo から自動判定 |
| 6-4 | ouster-sdk 未インストール時のガード | `cepf_sdk/parsers/ouster.py` | なし | `_require_ouster()` が明確な `ImportError` を送出 |
| 6-5 | Velodyne | `cepf_sdk/parsers/velodyne.py` | `parsers/base.py` | VLP-16 (2 firings/block) / VLP-32C 対応。全 CoordinateMode 対応。テスト 20本 PASS |
| 6-6 | TI Radar | `cepf_sdk/parsers/ti_radar.py` | `parsers/base.py` | TLV Type1 (XYZ+Doppler) / Type7 (SNR) 対応。自車速度補正。テスト 17本 PASS |
| 6-7 | Continental | `cepf_sdk/parsers/continental.py` | `parsers/base.py` | スケルトン実装 |

### フェーズ 7: テスト

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 7-1 | frame テスト | `tests/test_frame.py` | フェーズ 1 | CepfFrame の生成・アクセスが検証 |
| 7-2 | enums テスト | `tests/test_enums.py` | フェーズ 1 | 全列挙型の値が検証 |
| 7-3 | USC テスト | `tests/test_usc.py` | フェーズ 3 | forge, add_sensor, register_parser が検証 |
| 7-4 | Airy パーサーテスト | `tests/test_parsers/test_robosense_airy.py` | フェーズ 2 | ダミーパケットのデコードが検証 |
| 7-5 | Ouster パーサーテスト | `tests/test_parsers/test_ouster.py` | フェーズ 6 | モック LidarScan での変換が検証。ouster-sdk 未インストール時の ImportError も検証 |
| 7-6 | フィルターテスト | `tests/test_filters/test_*.py` | フェーズ 4 | 全フィルターの mask 正当性が検証 |
| 7-7 | 座標変換テスト | `tests/test_utils/test_coordinates.py` | フェーズ 5 | 往復変換の精度が検証 |

### フェーズ 8: apps/ 層の更新

| # | タスク | ファイル | 依存先 | 完了条件 |
|---|--------|---------|--------|---------|
| 8-1 | run_pipeline.py を USC 対応に書き換え | `apps/run_pipeline.py` | フェーズ 3 | USC.forge() ベースで動作 |
| 8-2 | processor.py を FilterPipeline 対応に更新 | `apps/processor.py` | フェーズ 4 | SDK のフィルターを使用 |
| 8-3 | 旧 `apps/processing/filters/` を廃止 | - | フェーズ 4 | SDK 側のフィルターに完全移行 |

---

## 8. 各ファイルの実装仕様

### 8.1 `cepf_sdk/enums.py`

```python
from enum import Enum, IntFlag

class SensorType(Enum):
    UNKNOWN = 0
    LIDAR = 1
    RADAR = 2

class CoordinateSystem(str, Enum):
    SENSOR_LOCAL = "sensor_local"
    VEHICLE_BODY = "vehicle_body"
    WORLD_ENU = "world_enu"
    WORLD_ECEF = "world_ecef"

class CoordinateMode(str, Enum):
    CARTESIAN = "cartesian"
    SPHERICAL = "spherical"
    BOTH = "both"
    CARTESIAN_WITH_RANGE = "cartesian_with_range"

class PointFlag(IntFlag):
    VALID = 0x0001
    DYNAMIC = 0x0002
    GROUND = 0x0004
    SATURATED = 0x0008
    NOISE = 0x0010
    RAIN = 0x0020
    MULTIPATH = 0x0040
    LOW_CONFIDENCE = 0x0080
```

### 8.2 `cepf_sdk/config.py`

```python
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from cepf_sdk.enums import SensorType, CoordinateMode

@dataclass
class SensorConfig:
    sensor_type: SensorType
    model: str
    serial_number: str = ""
    firmware_version: str = ""
    num_channels: int = 0
    horizontal_fov_deg: float = 360.0
    vertical_fov_deg: float = 45.0
    max_range_m: float = 200.0
    range_resolution_m: float = 0.1
    velocity_resolution_mps: float = 0.1

@dataclass
class Transform:
    translation: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    rotation_quaternion: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    )

    def to_matrix(self) -> np.ndarray:
        """4×4 同次変換行列を返す"""
        ...

    def inverse(self) -> "Transform":
        """逆変換を返す"""
        ...

@dataclass
class InstallationInfo:
    reference_description: str = ""
    reference_latitude: float = 0.0
    reference_longitude: float = 0.0
    reference_altitude: float = 0.0
    reference_datum: str = "WGS84"
    sensor_offset: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    sensor_offset_description: str = ""
```

### 8.3 `cepf_sdk/errors.py`

```python
class CEPFError(Exception):
    """CEPF SDK 基底例外"""

class ParseError(CEPFError):
    """パース失敗"""

class InvalidHeaderError(ParseError):
    """ヘッダー不正"""

class InvalidDataError(ParseError):
    """データ不正"""

class ChecksumError(ParseError):
    """チェックサム不一致"""

class ValidationError(CEPFError):
    """バリデーション失敗"""

class ConfigurationError(CEPFError):
    """設定エラー"""

class SensorNotFoundError(ConfigurationError):
    """未登録センサー"""

class ParserNotFoundError(ConfigurationError):
    """未登録パーサー"""

class SerializationError(CEPFError):
    """シリアライズ/デシリアライズ失敗"""
```

### 8.4 `cepf_sdk/usc.py` のスケルトン

```python
import json
from pathlib import Path
from cepf_sdk.config import SensorConfig, Transform, InstallationInfo
from cepf_sdk.enums import SensorType

class UnifiedSenseCloud:
    _parser_registry: dict[str, type] = {
        "robosense_airy": ...,
        "ouster_dome128": ...,
        # ...
    }

    def __init__(self):
        self._parsers: dict[str, RawDataParser] = {}
        self._transform = Transform()
        self._filters: list[Callable] = []
        self._output_coordinate = CoordinateSystem.SENSOR_LOCAL
        self._output_coordinate_mode = CoordinateMode.CARTESIAN
        self._installation: InstallationInfo | None = None

    @classmethod
    def register_parser(cls, name: str, parser_class: type) -> None: ...

    @classmethod
    def from_json(cls, config_path: str) -> "UnifiedSenseCloud":
        """
        JSON 設定ファイルから USC インスタンスを生成する（推奨メソッド）。
        
        プログラマーは cepf_sdk/ 内部を変更せず、
        自分たちのアプリケーション層（apps_py/, apps_ts/）に
        sensors.json を置いて管理するのが標準。
        
        JSON スキーマ:
            {
              "sensors": [
                {
                  "sensor_id": "lidar_1",
                  "parser_name": "robosense_airy",
                  "config": {
                    "sensor_type": "LIDAR",
                    "model": "RoboSense Airy",
                    "num_channels": 32,
                    ...
                  },
                  "transform": {
                    "translation": [x, y, z],
                    "rotation_quaternion": [w, x, y, z]
                  }
                }
              ],
              "installation": {
                "reference_description": "...",
                "reference_latitude": ...,
                ...
              }
            }
        
        引数:
            config_path (str): JSON ファイルパス
            
        戻り値:
            UnifiedSenseCloud: 初期化済みインスタンス
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        
        usc = cls()
        
        # センサー設定を読み込み
        for sensor_cfg in config_dict.get('sensors', []):
            sensor_config_dict = sensor_cfg.get('config', {})
            
            # sensor_type を文字列 → enum に変換
            if isinstance(sensor_config_dict.get('sensor_type'), str):
                sensor_config_dict['sensor_type'] = SensorType[
                    sensor_config_dict['sensor_type'].upper()
                ]
            
            sensor_config = SensorConfig(**sensor_config_dict)
            usc.add_sensor(
                sensor_id=sensor_cfg['sensor_id'],
                parser_name=sensor_cfg['parser_name'],
                config=sensor_config
            )
            
            # Transform 設定（存在すれば）
            if 'transform' in sensor_cfg:
                t = sensor_cfg['transform']
                usc.set_transform(
                    translation=t.get('translation', [0, 0, 0]),
                    rotation_quat=t.get('rotation_quaternion', [1, 0, 0, 0])
                )
        
        # Installation 設定（存在すれば）
        if 'installation' in config_dict:
            usc.set_installation(
                InstallationInfo(**config_dict['installation'])
            )
        
        return usc

    def add_sensor(self, sensor_id, parser_name, config) -> "UnifiedSenseCloud": ...
    def set_transform(self, translation, rotation_quat) -> "UnifiedSenseCloud": ...
    def set_output_coordinate(self, coord_sys) -> "UnifiedSenseCloud": ...
    def set_output_coordinate_mode(self, coord_mode) -> "UnifiedSenseCloud": ...
    def set_installation(self, installation) -> "UnifiedSenseCloud": ...
    def add_filter(self, filter_func) -> "UnifiedSenseCloud": ...
    def forge(self, sensor_id, raw_data, coordinate_mode=None) -> CepfFrame: ...
    def forge_multi(self, data_dict, coordinate_mode=None) -> CepfFrame: ...
    def get_parser(self, sensor_id) -> RawDataParser | None: ...
```

### 8.5 Ouster パーサーの実装仕様

> 詳細なコードはセクション 5.6 を参照。ここでは実装時のポイントをまとめる。

#### ファイル構成

| ファイル | クラス | 役割 |
|---------|--------|------|
| `parsers/ouster.py` | `OusterConfig` | Ouster 固有設定（source_url, meta_json, collate） |
| `parsers/ouster.py` | `OusterBaseParser` | Ouster 共通基底。`XYZLut` 座標変換、`parse_scan()` |
| `parsers/ouster.py` | `OusterLidarParser` | OS0/OS1/OS2 汎用パーサー |
| `parsers/ouster_dome128.py` | `OusterDome128Parser` | Dome 128 固有設定 |

#### ouster-sdk 遅延インポートのパターン

```python
# parsers/ouster.py の先頭
try:
    from ouster.sdk import open_source
    from ouster.sdk.core import SensorInfo, XYZLut
    _HAS_OUSTER = True
except ImportError:
    _HAS_OUSTER = False

def _require_ouster() -> None:
    if not _HAS_OUSTER:
        raise ImportError(
            "ouster-sdk が必要です: pip install cepf-sdk[ouster]"
        )
```

**重要**: `cepf_sdk/parsers/__init__.py` のパーサー登録マップでも遅延ロードが必要。
Ouster パーサーのインポートは `ouster-sdk` がインストールされている場合のみ行う。

```python
# cepf_sdk/parsers/__init__.py
_PARSER_MAP: dict[str, str] = {
    "robosense_airy": "cepf_sdk.parsers.robosense_airy.RoboSenseAiryParser",
    "ouster_dome128": "cepf_sdk.parsers.ouster_dome128.OusterDome128Parser",
    "ouster":         "cepf_sdk.parsers.ouster.OusterLidarParser",
}

def get_parser_class(name: str) -> type:
    """パーサー名から遅延インポートでクラスを取得する。"""
    import importlib
    dotted = _PARSER_MAP[name]
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
```

#### Ouster パーサー実装の重要定数（ouster_bridge3 からの参照値）

| 項目 | 値 | 出典 |
|------|-----|------|
| 距離スケール | `× 0.001` (mm → m) | ouster-sdk RANGE フィールド |
| 強度正規化 | `/ 65535.0` | reflectivity は uint16 |
| 信頼度計算 | `signal / max(noise, 1) / 100` → clip(0, 1) | ouster_bridge3 参照実装 |
| XYZ 座標変換 | `XYZLut(info)(scan)` → `(H, W, 3)` | ouster-sdk LUT ベース |
| ビーム角度 | `info.beam_altitude_angles`, `info.beam_azimuth_angles` | SensorInfo |

---

## 9. チェックリスト

### 9.1 フェーズ完了チェック

#### フェーズ 1: 基盤モジュール
- [ ] `enums.py` — 4 つの列挙型が定義されている
- [ ] `config.py` — `SensorConfig`, `Transform`, `InstallationInfo` が定義されている
- [ ] `errors.py` — 例外階層が完全に定義されている
- [ ] `frame.py` — 列挙型・設定クラスを使用するように更新されている
- [ ] `__init__.py` — 新モジュールの公開 API が re-export されている
- [ ] `pyproject.toml` — `packages.find` に変更 + `scipy` 依存追加 + `ouster` optional-dep 追加

#### フェーズ 2: ドライバー・パーサー基盤
- [ ] `drivers/__init__.py` — ドライバーパッケージが存在する
- [ ] `drivers/robosense_airy_driver.py` — `decode_packet()` が `AiryPacketData` を返す
- [ ] `drivers/robosense_airy_driver.py` — CepfFrame / CepfPoints を import していないこと
- [ ] `drivers/robosense_airy_driver.py` — 全定数（PKT_LEN, HDR, DB_SIZE 等）が移植されている
- [ ] `parsers/base.py` — `RawDataParser` ABC が定義されている
- [ ] `parsers/robosense_airy.py` — `RawDataParser` を継承し `parse()` / `validate()` が動作
- [ ] `parsers/robosense_airy.py` — 内部で `drivers/robosense_airy_driver.decode_packet()` を呼んでいる
- [ ] `parsers/__init__.py` — パーサー登録マップが定義されている
- [ ] `airy/decoder.py` — 後方互換ラッパーとして動作する
- [ ] 既存の `apps/run_pipeline.py` が壊れていないこと

#### フェーズ 3: USC
- [ ] `usc.py` — `UnifiedSenseCloud` クラスが実装されている
- [ ] `register_parser()` でカスタムパーサー追加が可能
- [ ] `add_sensor()` でセンサー登録が可能
- [ ] `forge()` で単一センサー変換が動作
- [ ] `forge_multi()` で複数センサー統合が動作
- [ ] 未登録 sensor_id で `SensorNotFoundError` が発生
- [ ] 未登録 parser_name で `ParserNotFoundError` が発生

#### フェーズ 4: フィルター
- [ ] `filters/base.py` — `PointFilter`, `FilterMode`, `FilterResult` が定義
- [ ] `filters/pipeline.py` — `FilterPipeline` が動作
- [ ] 領域カット系:
  - [ ] `CylindricalFilter` — 円筒形（`invert` 対応）
  - [ ] `SphericalFilter` — 球形（`invert` 対応）
  - [ ] `BoxFilter` — 直方体（`invert` 対応）
- [ ] 統計系:
  - [ ] `RadiusOutlierRemoval` — ROR
  - [ ] `StatisticalOutlierRemoval` — SOR
  - [ ] `VoxelDownsample` — ボクセル間引き
- [ ] 属性値系:
  - [ ] `IntensityFilter` — 強度フィルタ
  - [ ] `ConfidenceFilter` — 信頼度フィルタ
  - [ ] `FlagFilter` — フラグフィルタ
- [ ] 分類系:
  - [ ] `GroundClassifier` — 地面検出（FLAG モード）
  - [ ] `NoiseClassifier` — ノイズ検出（FLAG モード）
- [ ] 全フィルターが `compute_mask()` のみ実装で動作すること
- [ ] MASK / FLAG モード切替が正常に動作すること

#### フェーズ 5: ユーティリティ
- [ ] `utils/coordinates.py` — `spherical_to_cartesian`, `cartesian_to_spherical`, `lla_to_ecef`, `ecef_to_lla`
- [ ] `utils/quaternion.py` — `quaternion_to_rotation_matrix`, `rotation_matrix_to_quaternion`
- [ ] `utils/io.py` — `load_cepf_file`, `save_cepf_file`

#### フェーズ 6: 追加パーサー
- [ ] `parsers/ouster.py` — `OusterBaseParser` + `OusterLidarParser` + `OusterConfig` が実装されている
- [ ] `parsers/ouster.py` — `_require_ouster()` による ouster-sdk 未インストール時のガードが動作
- [ ] `parsers/ouster.py` — `open_source_iter()` でライブセンサ / PCAP 再生の両方に対応
- [ ] `parsers/ouster.py` — `parse_scan(LidarScan)` が `XYZLut` 経由で CepfFrame を生成
- [ ] `parsers/ouster.py` — 全 `CoordinateMode` (CARTESIAN, SPHERICAL, BOTH, CARTESIAN_WITH_RANGE) に対応
- [ ] `parsers/ouster_dome128.py` — `OusterDome128Parser` が Dome 128 固有設定で `OusterBaseParser` を継承
- [ ] `parsers/__init__.py` — Ouster パーサーも遅延ロードでパーサー登録マップに含まれている
- [ ] `pip install cepf-sdk[ouster]` で ouster-sdk が入り Ouster パーサーが動作
- [x] Velodyne パーサー（VLP-16/32C 実装済み）— `tests/test_parsers/test_velodyne.py` (20テスト)
- [x] TI Radar パーサー（AWR1843/IWR6843 実装済み）— `tests/test_parsers/test_ti_radar.py` (17テスト)
- [ ] Continental パーサー — スタブのみ

#### フェーズ 7: テスト
- [ ] `tests/test_frame.py` — CepfFrame の生成・アクセス
- [ ] `tests/test_enums.py` — 列挙型の値
- [ ] `tests/test_usc.py` — forge, add_sensor, register_parser
- [ ] `tests/test_parsers/` — ダミーパケットのデコード
- [ ] `tests/test_parsers/test_ouster.py` — モック LidarScan 変換、ouster-sdk 未インストール時ガード
- [ ] `tests/test_filters/` — 全フィルターの mask 正当性
- [ ] `tests/test_utils/` — 座標変換の往復精度

#### フェーズ 8: apps/ 更新
- [ ] `apps/run_pipeline.py` が USC.forge() ベースで動作
- [ ] `apps/processor.py` が FilterPipeline を使用
- [ ] `apps/processing/filters/` が廃止・SDK 側に統合

### 9.2 品質チェック

- [ ] 全モジュールに型ヒントが付与されている
- [ ] 公開クラス・関数に docstring がある
- [ ] `pyproject.toml` の packages 設定で全サブパッケージが含まれている
- [ ] `pip install -e .` でインストールが成功する
- [ ] `pip install -e ".[ouster]"` で ouster-sdk 込みのインストールが成功する
- [ ] ouster-sdk 未インストール時に Ouster パーサー以外の機能が正常動作する
- [ ] 既存の `from cepf_sdk.airy import UdpAiryDecoder` が動作する（後方互換）
- [ ] `pytest` で全テストが PASS する

---

## 10. 用語集・参照情報

### 10.1 用語集

| 用語 | 説明 |
|------|------|
| **CEPF** | CubeEarth Point Format。LiDAR/Radar の点群を統一的に扱うデータフォーマット |
| **USC** | UnifiedSenseCloud。CEPF フォーマットへの変換を行うファクトリークラス |
| **ドライバー** | センサ固有のパケットバイナリ解析を行う低レベル層。CepfFrame を知らない。自前実装（Airy）または外部 SDK（Ouster）|
| **パーサー** | ドライバーまたは外部 SDK の出力を CepfFrame に変換するクラス |
| **forge** | USC のメインメソッド。「鍛造する」の意。生データ → CepfFrame 変換 |
| **点群 (Point Cloud)** | LiDAR/Radar で取得した 3D 空間上の点の集合 |
| **フレーム (Frame)** | 一定時間内に収集した点群のまとまり。動画の 1 フレームに相当 |
| **列指向 (Column-oriented)** | フィールドごとに配列を持つデータ構造（行指向の逆）|
| **ROR** | Radius Outlier Removal。半径内の近傍点数による外れ値除去 |
| **SOR** | Statistical Outlier Removal。k 近傍平均距離の統計的外れ値除去 |
| **frozen** | `@dataclass(frozen=True)` で生成されたイミュータブルなオブジェクト |
| **coordinate_mode** | 座標の表現形式。cartesian / spherical / both / cartesian_with_range |
| **PointFlag** | 各点に付与するビットフラグ（VALID, GROUND, NOISE 等）|
| **ouster-sdk** | Ouster 公式 Python SDK（`pip install ouster-sdk`）。パケットデコード・座標変換を提供 |
| **LidarScan** | ouster-sdk のクラス。1 回転分のスキャンデータを格納。フィールド（RANGE, REFLECTIVITY 等）を持つ |
| **XYZLut** | ouster-sdk のクラス。SensorInfo からルックアップテーブルを生成し、LidarScan → (H,W,3) XYZ 座標を高速変換 |
| **SensorInfo** | ouster-sdk のクラス。センサメタデータ（prod_line, beam_angles, format 等）を格納 |
| **open_source** | ouster-sdk の関数。ライブセンサ（ホスト名）または PCAP ファイルを開き、LidarScan イテレータを返す |
| **ChanField** | ouster-sdk の列挙型。RANGE, REFLECTIVITY, SIGNAL, NEAR_IR 等のフィールド ID |
| **optional dependency** | `pip install cepf-sdk[ouster]` のように、extras で指定する任意依存パッケージ |

### 10.2 参照ドキュメント

| ドキュメント | パス | 内容 |
|------------|------|------|
| CEPF/USC 仕様書 | `docs/CEPF_USC_Specification_v1_2.md` | フォーマット定義、クラス仕様、全パーサー仕様 |
| SDK 使い方ガイド | `docs/readme.md` | 現在の SDK の使い方（初学者向け） |
| 本ドキュメント | `docs/cepf-sdk-refactoring-guide.md` | リファクタリング手順・設計方針 |
| ouster-sdk ドキュメント | https://static.ouster.dev/sdk-docs/ | Ouster 公式 SDK の API リファレンス |
| ouster_bridge3 参照実装 | `../ouster_bridge3/ouster_to_ws/ouster_to_ws.py` | ouster-sdk を使った動作例（open_source, XYZLut） |
| ouster_bridge3 解析ドキュメント | `../ouster_bridge3/readme-chosa.md` | Ouster Bridge 3 のデータフロー・座標変換式の詳細解説 |

### 10.3 現在の `decoder.py` の重要定数（移植時の参照）

| 定数 | 値 | 意味 |
|------|----|------|
| `PKT_LEN` | 1248 | Airy 1 パケットのバイト数 |
| `HDR` | 42 | ヘッダ長 |
| `DB_SIZE` | 148 | 1 Data Block のサイズ |
| `N_DB` | 8 | 1 パケット内の Data Block 数 |
| `CH_PER_DB` | 48 | 1 Data Block 内のチャンネル数 |
| `DIST_MASK` | 0x3FFF | 14bit 距離値のマスク |
| `FLAG_EXPECT` | 0xFFEE | 有効な Data Block のフラグ値 |
| `TICK_OFF` | 26 | タイムスタンプのバイトオフセット |
| `dist_scale_m` | 0.002 | 距離スケール（生値 × 0.002 = メートル） |
| `intensity_div` | 255.0 | 強度正規化の除数 |

### 10.4 AI への実装指示テンプレート

各フェーズの実装を AI に依頼する際は、以下の形式で指示すること：

```
## 実装依頼

### 対象フェーズ
フェーズ X-Y: [タスク名]

### 実装するファイル
- `cepf_sdk/[ファイルパス]`

### 参照すべきドキュメント
- `docs/CEPF_USC_Specification_v1_2.md` のセクション X.X
- `docs/cepf-sdk-refactoring-guide.md` のセクション X.X

### 完了条件
- [チェックリストから該当項目を転記]

### 制約
- 既存の `apps/` のコードを壊さないこと
- Python 3.10+ の型ヒントを使用すること
- `@dataclass` を活用すること
```

---

*本ドキュメントは cepf-sdk v0.1.0 → v0.2.0 へのリファクタリング計画として作成。仕様書 CEPF_USC_Specification_v1_2.md (v1.2.0) に準拠。*

---

## 付録 A: 統合アーキテクチャ設計 — Q&A と最終フォルダ構成

> **背景**: ouster_bridge3 プロジェクトの機能（WebSocket サーバー / Three.js ビジュアライザ / ボクセル化）を cepf-sdk エコシステムに統合するにあたり、設計上の疑問と回答をまとめ、最終的なフォルダ構成を提案する。

### A.1 設計 Q&A

---

#### Q1. 現在の `airy/` は `drivers/` の下に置くのが設計的に美しいか？

**A: いいえ。`airy/` フォルダは 2 つのレイヤーにまたがっています。**

現在の `airy/decoder.py` は UDP 受信 → バイナリ解析 → 座標変換 → CepfFrame 生成をすべて担っている。これを正しく分離すると：

| 分離先 | 内容 |
|--------|------|
| `drivers/robosense_airy_driver.py` | パケット定数・バイナリデコード（CepfFrame を知らない） |
| `parsers/robosense_airy.py` | drivers/ を呼び出し → CepfFrame に変換するアダプタ |
| `airy/` （ルート直下に残す） | **後方互換ラッパー**。内部で `parsers/robosense_airy.py` に委譲するだけ |

`airy/` を丸ごと `drivers/` に入れるのは間違い。`drivers/` はバイナリ解析のみ。

---

#### Q2. USC は `parsers/` の中か？

**A: いいえ。USC（`usc.py`）は `cepf_sdk/` 直下に配置する。**

USC は parsers と filters を **束ねるマネージャー** であり、パーサーそのものではない。

```
cepf_sdk/
├── usc.py          ← ★ ここ（parsers の「上位」に位置）
├── parsers/        ← USC に登録される個別パーサー
├── filters/        ← USC がパイプラインとして適用
└── ...
```

USC は「どのパーサーを使うか」を決定し、フィルタ適用・座標変換・統合まで行う。

---

#### Q3. Ouster SDK を使う場合、`parsers/` の下から呼び出す形か？

**A: その通り。**

```
parsers/
├── ouster.py            ← ouster-sdk の open_source() / XYZLut() を呼ぶ
│                           → LidarScan を CepfFrame に変換するアダプタ
└── robosense_airy.py    ← drivers/ の自前デコーダを呼ぶ
```

Ouster の場合は `drivers/` にファイルは不要。ouster-sdk がドライバー相当。

---

#### Q4. フィルタ後の WebSocket 転送はどこで実装するか？

**A: `transport/` フォルダを新設するのが設計上美しい。**

WebSocket はデータの「出口」であり、SDK のコア機能（parsers/filters）とも、アプリケーション固有ロジック（apps/）とも異なるレイヤー。「`ouster_to_ws` を `cepf_to_ws` に改名」という発想は正しいが、それを **トランスポート層** として独立させる：

```
cepf_sdk/
├── transport/              ← ★ 新設
│   ├── __init__.py
│   ├── base.py             # TransportBase 抽象基底
│   ├── websocket.py        # WebSocket 送信（asyncio + websockets）
│   └── http_server.py      # 静的ファイル配信（Three.js viewer 用）
```

**理由:**
- `apps/` に入れると再利用性が低い（他のアプリがコピペする）
- SDK の一部として提供すれば、どのアプリからも `from cepf_sdk.transport import WebSocketTransport` で使える
- 将来の拡張: MQTT, gRPC, ROS2 Topic も同じ `transport/` に追加できる

---

#### Q5. `utils/` は主に `parsers/` から呼び出されるものか？

**A: `parsers/` だけではない。全レイヤーから使われる汎用ツール。**

| 呼び出し元 | utils の関数 |
|-----------|-------------|
| `parsers/` | `coordinates.py`（球面→直交変換） |
| `filters/` | `coordinates.py`（ECEF 変換）, `quaternion.py`（回転） |
| `transport/` | `io.py`（シリアライズ） |
| `apps/` | すべて |

`utils/` は依存関係グラフの **最下位** に位置し、SDK 内の誰からでも呼べる。

---

#### Q6. `ws/` フォルダは何か？

**A: 現在の `ouster_bridge3/ws/` は空フォルダ。**

おそらく WebSocket サーバー実装の予定地だったが、実際は `ouster_to_ws/ouster_to_ws.py` に WebSocket サーバー機能が直接実装されているため未使用。新設計では `transport/` に統合する。

---

#### Q7. ビジュアライザは現在どこに実装されているか？ cepf-sdk に統合するなら？

**A: 現在は `ouster_bridge3/three/` に Three.js ベースで実装されている。**

cepf-sdk に統合する場合は **`viewer/`** として独立ディレクトリにする：

```
cepf-sdk/
├── viewer/                 ← ★ 新設（フロントエンド）
│   ├── package.json
│   ├── tsconfig.json
│   ├── webpack.config.js
│   ├── index.html
│   ├── src/
│   │   ├── index.ts        # エントリーポイント
│   │   ├── voxel.ts         # ローカルボクセル化（現行の VoxelGrid）
│   │   ├── spatial-id.ts    # 空間ID（vendor ライブラリ使用）
│   │   └── stats.ts         # パフォーマンス表示
│   └── styles/
│       └── style.css
```

**`cepf_sdk/` の下ではなく、cepf-sdk リポジトリのルート直下** に置く理由：
- TypeScript / Node.js のプロジェクト（Python SDK とはビルドシステムが完全に別）
- `cepf_sdk/` は Python パッケージ（pip installable）であり、JS は含めるべきでない
- `viewer/` は `transport/websocket.py` の **クライアント側** という位置づけ

---

#### Q8. Three.js はそのまま cepf-sdk の下に置けばよいか？

**A: Q7 の通り、`viewer/` としてリポジトリルート直下に配置。`cepf_sdk/` Python パッケージの内部には含めない。**

---

#### Q9. WebSocket 受信側＋空間ID化のフォルダ名は？

**A: WebSocket 受信は `ws-client/` に独立。空間ID化は `voxel/` 内。**

現在の ouster_bridge3 の受信側機能は以下のように分離される：
- WebSocket クライアント → `ws-client/src/ws-connection.ts`（ヘッドレス可）
- ローカルボクセル化 → `voxel/src/voxel-grid.ts`
- 空間ID化（vendor ライブラリ使用） → `voxel/src/spatial-id-converter.ts`
- Three.js シーン管理 → `viewer/src/index.ts`（WebSocket を知らない）

```
ws-client/src/
├── ws-connection.ts       # WebSocket 接続管理（再接続ハンドリング付き）
├── point-stream.ts        # 点群ストリーム（callback / AsyncIterator）
└── types.ts               # PointData, ConnectionConfig 型

voxel/src/
├── voxel-grid.ts          # ローカルボクセル化（float座標ベース, 高速）
├── spatial-id-converter.ts # 空間ID化（vendor/alogs 使用, 緯度経度ベース）
└── types.ts               # VoxelKey, VoxelSnapshot 型

viewer/src/
├── index.ts               # Three.js シーン管理のみ（WS を知らない）
├── renderers/
│   ├── voxel-renderer.ts  # ボクセル描画（InstancedMesh 管理）
│   └── spatial-id-renderer.ts
└── stats.ts
```

**apps_ts/ が ws-client → voxel → viewer をつなぐ配線役。**

**ouster_bridge3 のフォルダ名を変えるべきか？** → ouster_bridge3 は廃止し、機能を cepf-sdk に統合する。

---

### A.2 全体データフローパイプライン

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Python 側 (cepf-sdk)                         │
│                                                                     │
│  センサ ─→ [drivers/]   ─→ [parsers/]  ─→ [usc.py]  ─→ [filters/] │
│            バイナリ解析      CepfFrame生成    統合管理     点群フィルタ│
│  Airy:  自前ドライバー   AiryParser                    range/cyl... │
│  Ouster: ouster-sdk     OusterParser                  stat/ror...  │
│                                                                     │
│                                              ↓                      │
│                                         [transport/]                │
│                                         WebSocket送信               │
│                                         HTTP配信                    │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │ WebSocket
                                          ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     TypeScript 側                                    │
│                                                                     │
│  ws-client/ ── WebSocket受信（ヘッドレス可）                        │
│       ↓ PointData[]                                                │
│  voxel/ ── ボクセル計算（ヘッドレス可）                              │
│       ↓ VoxelSnapshot                                              │
│  viewer/ ── Three.js で 3D 描画（ブラウザ専用）                     │
│              InstancedMesh + 密度色分け                              │
│                                                                     │
│  apps_ts/ が上記を配線する「接着剤」                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

### A.3 最終フォルダ構成（統合版）

```
sass/                                  # ========== リポジトリルート ==========名前かえちゃいました。
├── pyproject.toml
├── README.md
│
├── docs/
│   ├── readme.md
│   ├── CEPF_USC_Specification_v1_4.md
│
│   ╔══════════════════════════════════════════════════════════════════╗
│   ║               Python SDK (pip )                                  ║
│   ╚══════════════════════════════════════════════════════════════════╝
│
├── cepf_sdk/                              # ========== SDK コア (Python) ==========
│   ├── __init__.py                        #   公開 API
│   ├── frame.py                           #   CepfFrame, CepfMetadata
│   ├── types.py                           #   CepfPoints, NDArray
│   ├── enums.py                           #   SensorType, CoordinateSystem, etc.
│   ├── config.py                          #   SensorConfig, Transform
│   ├── errors.py                          #   エラー階層
│   ├── usc.py                             #   UnifiedSenseCloud マネージャー
│   │
│   ├── drivers/                           # ── センサ固有バイナリ解析 ──
│   │   ├── __init__.py
│   │   └── robosense_airy_driver.py       #   Airy パケットデコード（自前）
│   │                                      #   ※ Ouster は ouster-sdk が担う
│   │
│   ├── parsers/                           # ── センサ → CepfFrame 変換 ──
│   │   ├── __init__.py
│   │   ├── base.py                        #   RawDataParser 抽象基底
│   │   ├── robosense_airy.py              #   Airy（drivers/ 呼出）
│   │   ├── ouster.py                      #   Ouster（ouster-sdk 呼出）
│   │   ├── velodyne.py                    #   Velodyne VLP-16/32C（実装済み）
│   │   ├── ti_radar.py                    #   TI Radar AWR/IWR（実装済み）
│   │   └── continental.py                 #   Continental（スタブ）
│   │
│   ├── filters/                           # ── 点群フィルタリング ──
│   │   ├── __init__.py
│   │   ├── base.py                        #   PointFilter 抽象基底
│   │   ├── pipeline.py                    #   FilterPipeline
│   │   ├── range/                         #   領域カット系
│   │   ├── statistical/                   #   統計系（ROR, SOR, ボクセル）
│   │   ├── attribute/                     #   属性値ベース
│   │   └── classification/                #   分類・ラベリング
│   │
│   ├── transport/                         # ── データ転送層　──
│   │   ├── __init__.py
│   │   ├── base.py                        #   TransportBase 抽象基底
│   │   ├── websocket_server.py            #   WebSocket サーバー
│   │   └── http_server.py                 #   HTTP 静的ファイル配信
│   │
│   ├── utils/                             # ── 汎用ユーティリティ ──
│   │   ├── __init__.py
│   │   ├── coordinates.py                 #   球面⇔直交, LLA⇔ECEF
│   │   ├── quaternion.py                  #   回転行列
│   │   └── io.py                          #   ファイル I/O
│   │
│   └── airy/                              # ── 後方互換ラッパー ──
│       ├── __init__.py
│       └── decoder.py                     #   → parsers/ に委譲
│
├── apps/                                  # ========== アプリケーション ==========
│   ├── __init__.py
│   ├── run_pipeline.py                    #   パイプラインエントリーポイント
│   └── processor.py                       #   アプリ固有の後段処理（ロギング等）
│
│   ╔══════════════════════════════════════════════════════════════════╗
│   ║          TypeScript (npm )                                       ║
│   ╚══════════════════════════════════════════════════════════════════╝
│
├── voxel/                                 # ========== ボクセル計算エンジン ==========
│   ├── package.json                       #   Three.js 無依存・ヘッドレス可
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                       #   エクスポート
│   │   ├── voxel-grid.ts                  #   リアルタイムボクセルグリッド（現フレーム）
│   │   ├── background-voxel-map.ts        #   背景ボクセルマップ（蓄積・学習）
│   │   ├── voxel-diff.ts                  #   スナップショット差分計算
│   │   ├── spatial-id-converter.ts        #   空間ID変換（vendor/alogs 使用）
│   │   └── types.ts                       #   VoxelKey, VoxelState, VoxelSnapshot, VoxelDiffEntry 型
│   └── tests/
│
├── ws-client/                             # ========== WebSocket クライアント（★ 新設）==========
│   ├── package.json                       #   ブラウザ / Node.js 両対応・ヘッドレス可
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                       #   エクスポート
│   │   ├── ws-connection.ts               #   WebSocket 接続管理（再接続・切断ハンドリング）
│   │   ├── point-stream.ts                #   点群ストリーム（onMessage コールバック / AsyncIterator）
│   │   └── types.ts                       #   PointData, ConnectionConfig, StreamOptions 型
│   └── tests/
│
├── viewer/                                # ========== 3D ビジュアライザ（描画専用）==========
│   ├── package.json
│   ├── tsconfig.json
│   ├── webpack.config.js
│   ├── index.html
│   ├── src/
│   │   ├── index.ts                       #   Three.js シーン管理（※ WebSocket は ws-client/ に分離）
│   │   ├── renderers/                     #   描画レイヤー（Three.js 依存）
│   │   │   ├── voxel-renderer.ts          #   voxel/ → InstancedMesh 描画
│   │   │   └── spatial-id-renderer.ts     #   voxel/ → GIS座標描画
│   │   ├── overlays/                      #   オーバーレイ表示群
│   │   │   ├── drone-sprite.ts            #   ドローンスプライト表示
│   │   │   └── intrusion-highlight.ts     #   侵入ボクセルハイライト
│   │   └── stats.ts                       #   パフォーマンス計測
│   └── styles/
│       └── style.css
│
├── vendor/                                # ========== 空間ID TS ライブラリ ==========
│   ├── alogs/                             #   グリッドID ⇔ 緯度経度 変換
│   ├── models/                            #   IGrid, IGrid3D, ILatLng 型定義
│   └── util/                              #   Util, HitTest ユーティリティ
│
└── tests/                                 # ========== テスト（Python）==========
    ├── test_parsers/
    ├── test_filters/
    ├── test_transport/
    └── test_utils/
```

---

### A.4 `voxel/` の分離 — ボクセル計算を viewer から独立させる

> **質問**: ボクセル系を viewer と分離できないか？

**答え: `voxel/` を独立パッケージとして分離する。Three.js に依存しない純粋な座標計算エンジン。**

#### なぜ分離するか？

現在の `ouster_bridge3/three/src/voxel.ts` は **座標計算** と **Three.js 描画** が混在している。これを分離すると：

- `detector/` が viewer を経由せずにボクセル計算を使える
- サーバーサイド Node.js でヘッドレス実行できる
- viewer は `voxel/` の結果を「描画するだけ」になる

#### 3パッケージの責任分担

| パッケージ | 関心 | Three.js 依存 | ヘッドレス？ |
|-----------|------|:-------------:|:-----------:|
| `ws-client/` | WebSocket 通信（点群ストリーム受信） | × | ○ |
| `voxel/` | 座標計算・ボクセルグリッド生成・空間ID変換 | × | ○ |
| `viewer/` | Three.js で 3D 描画 | ○ | × |
| `detector/` | 侵入判定ロジック | × | ○ |

#### 言語とパッケージの独立性

```
┌──────────────────────────────────────────────────────────────┐
│ リポジトリ: sass                                             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌─────────────────────────────────────┐
│  cepf_sdk/ (Python)  │      │    TypeScript パッケージ群            │
│                      │      │                                     │
│  pip install対象     │      │ ┌──────────┐  ┌──────────────────┐  │
│                      │      │ │ws-client/│  │ viewer/          │  │
│  drivers/            │      │ │ WS受信   │  │ 3D 描画          │  │
│  parsers/            │      │ │ ヘッドレス│  │ Three.js 依存    │  │
│  filters/            │      │ └────┬─────┘  └──────────────────┘  │
│  transport/  ◀───WS──┤      │      │                               │
│  (WebSocket送信)    │      │ ┌────┴─────┐  ┌──────────────────┐  │
│                      │      │ │ voxel/   │  │ detector/        │  │
│                      │      │ │ 座標計算 │  │ 侵入判定         │  │
│                      │      │ │ ヘッドレス│  │ ヘッドレス       │  │
└──────────────────────┘      │ └──────────┘  └──────────────────┘  │
                              │                                     │
                              │ ┌──────────┐  ┌──────────────────┐  │
                              │ │mqtt-clnt/│  │ apps_ts/         │  │
                              │ │ MQTT通信 │  │ エントリーポイント│  │
                              │ └──────────┘  └──────────────────┘  │
                              │                                     │
                              │ ┌──────────────────────────────┐    │
                              │ │ vendor/  空間IDライブラリ     │    │
                              │ └──────────────────────────────┘    │
                              └─────────────────────────────────────┘
```

#### ボクセル化・差分・侵入検知 — 分離後の配置

| 機能 | 実装場所 | 依存 | 用途 |
|------|---------|------|------|
| **リアルタイムボクセル化** | `voxel/src/voxel-grid.ts` | なし | 現フレームの点群をボクセル化 |
| **背景ボクセル記憶** | `voxel/src/background-voxel-map.ts` | なし | 背景モデルを蓄積・学習 |
| **スナップショット差分** | `voxel/src/voxel-diff.ts` | なし | 現在 vs 背景の差分をボクセル単位で算出 |
| **空間ID変換** | `voxel/src/spatial-id-converter.ts` | vendor/alogs | 緯度経度 → グリッドID 変換 |
| **侵入判定ポリシー** | `detector/src/intrusion-detector.ts` | voxel/ | VoxelDiff を閾値で判定 → IntrusionEvent |
| **閾値アルゴリズム** | `detector/src/threshold/*.ts` | なし | 固定閾値/適応的平均/適応的標準偏差 |
| **ボクセル描画** | `viewer/src/renderers/voxel-renderer.ts` | voxel/ + Three.js | InstancedMesh 描画 |
| **侵入ハイライト** | `viewer/src/overlays/intrusion-highlight.ts` | Three.js | 侵入ボクセルの色分け表示 |

**考え方:**
- `voxel/` = **「何が変わったか」（データ）** を提供
- `detector/` = **「それは侵入か？」（ポリシー）** を判定
- `viewer/` = **「結果をどう見せるか」（表示）** を担当

#### 具体的なコード構成

```typescript
// ── voxel/ パッケージ（Three.js 無依存）──

// voxel/src/voxel-grid.ts
// 純粋な座標計算のみ。Three.js にもブラウザにも依存しない
export class VoxelGrid {
  private voxels = new Map<string, VoxelState>();
  
  addPoint(x: number, y: number, z: number, frameId: number): void {
    const key = this.getVoxelKey(x, y, z);
    // float座標でのボクセルキー生成
  }

  /** 現在のボクセル状態のスナップショットを返す */
  snapshot(): VoxelSnapshot {
    return new Map(this.voxels);
  }

  /** ボクセルキーからボクセル中心座標を返す */
  keyToCenter(key: string): { x: number; y: number; z: number } { ... }
}

// voxel/src/spatial-id-converter.ts
// vendor/alogs を使用。座標変換のみ
import Encode from '../../vendor/alogs/Encode';
import Decode from '../../vendor/alogs/Decode';

export function latLngToGridID(lat: number, lng: number, alt: number): string {
  return Encode.LatLngTo3DID(lat, lng, alt);
}

export function gridIDToGridBounds(gridID: string) {
  return Decode.gridIdTo3DLocation(gridID);
}

// voxel/src/types.ts
export type VoxelKey = string;
export interface VoxelState { count: number; lastUpdated: number; }
export type VoxelSnapshot = Map<VoxelKey, VoxelState>;

/** 背景モデル：各ボクセルの統計値 */
export interface BackgroundStats {
  mean: number;      // 平均ポイント数
  stddev: number;    // 標準偏差
  samples: number;   // 学習フレーム数
}

/** 差分エントリ：背景と現在の差を表す */
export interface VoxelDiffEntry {
  key: VoxelKey;
  currentCount: number;
  backgroundMean: number;
  delta: number;          // currentCount - backgroundMean
}

// voxel/src/background-voxel-map.ts
import { VoxelSnapshot, VoxelKey, BackgroundStats } from './types';

/** 背景ボクセルマップ ── 「履歴付きボクセルグリッド」 */
export class BackgroundVoxelMap {
  private stats = new Map<VoxelKey, BackgroundStats>();

  /** スナップショットを取り込んで背景モデルを更新（移動平均） */
  learn(snapshot: VoxelSnapshot): void { ... }

  /** 指定キーの背景統計を取得 */
  get(key: VoxelKey): BackgroundStats | undefined { ... }

  /** 学習フレーム数が閾値を超えたか（安定判定） */
  isStable(minSamples: number): boolean { ... }
}

// voxel/src/voxel-diff.ts
import { VoxelSnapshot, VoxelDiffEntry } from './types';
import { BackgroundVoxelMap } from './background-voxel-map';

/** 背景と現在フレームの差分を算出 ── 「何が変わったか」 */
export function computeDiff(
  current: VoxelSnapshot,
  background: BackgroundVoxelMap
): VoxelDiffEntry[] { ... }
```

```typescript
// ── ws-client/ パッケージ（ブラウザ / Node.js 両対応、ヘッドレス可）──

// ws-client/src/types.ts
export interface ConnectionConfig {
  url: string;           // "ws://192.168.1.100:8765"
  reconnectInterval?: number;  // 自動再接続間隔 (ms)
  maxRetries?: number;
}

export interface PointData {
  x: number; y: number; z: number;
  intensity?: number;
  timestamp?: number;
}

// ws-client/src/ws-connection.ts
export class WsConnection {
  private socket: WebSocket | null = null;

  constructor(private config: ConnectionConfig) {}

  connect(): void { ... }
  disconnect(): void { ... }

  /** コールバック方式 — viewer 向け */
  onMessage(callback: (points: PointData[]) => void): void { ... }

  /** AsyncIterator 方式 — detector 向け（ヘッドレス） */
  async *frames(maxFrames?: number): AsyncGenerator<PointData[]> { ... }
}

// ws-client/src/point-stream.ts
/** 複数の WsConnection を束ねるマルチソースストリーム（将来拡張） */
export class PointStream {
  addSource(id: string, connection: WsConnection): void { ... }
  async *mergedFrames(): AsyncGenerator<{ sourceId: string; points: PointData[] }> { ... }
}
```

```typescript
// ── viewer/ パッケージ（Three.js 依存、描画のみ — WebSocket を知らない）──

// viewer/src/index.ts
// Three.js シーン管理のみ。データの取得方法は知らない。
import * as THREE from 'three';
import { VoxelRenderer } from './renderers/voxel-renderer';
import { SpatialIDRenderer } from './renderers/spatial-id-renderer';

export class ViewerApp {
  private scene: THREE.Scene;
  private voxelRenderer: VoxelRenderer;
  private spatialIDRenderer: SpatialIDRenderer;

  constructor(container: HTMLElement) {
    this.scene = new THREE.Scene();
    this.voxelRenderer = new VoxelRenderer(this.scene);
    this.spatialIDRenderer = new SpatialIDRenderer(this.scene);
    // Three.js カメラ、レンダラー、ライト等の初期化...
  }

  /** 外部から点群を渡して描画する（データソースを問わない） */
  updateVoxels(snapshot: VoxelSnapshot): void {
    this.voxelRenderer.update(snapshot);
  }

  render(): void {
    // requestAnimationFrame ループ
  }
}
```

```typescript
// ── apps_ts/ が ws-client → voxel → viewer を接続する ──

// apps_ts/src/main-viewer.ts（抜粋）
import { WsConnection } from '../ws-client/src/ws-connection';
import { VoxelGrid } from '../voxel/src/voxel-grid';
import { ViewerApp } from '../viewer/src/index';

const ws = new WsConnection({ url: 'ws://192.168.1.100:8765' });
const voxelGrid = new VoxelGrid(1.0);
const viewer = new ViewerApp(document.getElementById('app')!);

ws.connect();
ws.onMessage((points) => {
  for (const p of points) voxelGrid.addPoint(p.x, p.y, p.z, frameId);
  viewer.updateVoxels(voxelGrid.snapshot());
});
```

```typescript
// ── detector/ パッケージ（ヘッドレス、voxel/ に依存 — ポリシー層）──

// detector/src/threshold/threshold-strategy.ts
/** 閾値戦略の抽象インタフェース */
export interface ThresholdStrategy {
  isIntrusion(delta: number, bgMean: number, bgStddev: number): boolean;
}

// detector/src/threshold/static-threshold.ts
export class StaticThreshold implements ThresholdStrategy {
  constructor(private threshold: number) {}
  isIntrusion(delta: number): boolean { return delta > this.threshold; }
}

// detector/src/threshold/adaptive-stddev.ts
export class AdaptiveStddevThreshold implements ThresholdStrategy {
  constructor(private sigma: number = 2.0) {}
  isIntrusion(delta: number, _mean: number, stddev: number): boolean {
    return delta > this.sigma * stddev;
  }
}

// detector/src/intrusion-detector.ts
import { VoxelDiffEntry } from '../../voxel/src/types';
import { ThresholdStrategy } from './threshold/threshold-strategy';

export interface IntrusionEvent {
  key: string;
  delta: number;
  timestamp: number;
}

/** 侵入検知器 ── 「それは侵入か？」を判定する */
export class IntrusionDetector {
  constructor(private strategy: ThresholdStrategy) {}

  /** VoxelDiff（voxel/ が算出）を受け取り、閾値で判定 */
  evaluate(diffs: VoxelDiffEntry[]): IntrusionEvent[] {
    return diffs
      .filter(d => this.strategy.isIntrusion(d.delta, d.backgroundMean, 0))
      .map(d => ({ key: d.key, delta: d.delta, timestamp: Date.now() }));
  }
}
```

#### 依存の流れ（voxel/ + ws-client/ 分離後）

```
apps_ts/
├── main-viewer.ts ──→ ws-client/ ──→（Python transport/ から WS 受信）
│                  ──→ voxel/     ──→ vendor/
│                  ──→ viewer/    ──→ voxel/（スナップショット描画のみ）
│                  ──→ mqtt-client/
│
└── main-detector.ts ──→ ws-client/ ──→（Python transport/ から WS 受信）
                     ──→ voxel/     ──→ vendor/
                     ──→ detector/  ──→ voxel/
                     ──→ mqtt-client/

ws-client/   → （外部依存のみ: WebSocket API）
voxel/       → vendor/  （空間ID変換時のみ）
viewer/      → voxel/   （スナップショット描画）
detector/    → voxel/   （ボクセルスナップショット取得）
mqtt-client/ → （外部依存のみ: mqtt.js）
vendor/      → （独立）
```

**核心:**
- **ws-client/** = データ取得層（どこから来るか）
- **voxel/** = 座標計算エンジン（何を計算するか）
- **viewer/** = 描画層（どう見せるか）— データソースを知らない
- **detector/** = 分析層（どう判定するか）

---

### A.5 設計原則のまとめ（修正版）

| 原則 | 適用 |
|------|-----|
| **言語の分離** | Python（`cepf_sdk/`, `apps_py/`）/ TypeScript（`ws-client/`, `voxel/`, `viewer/`, `detector/`, `mqtt-client/`, `apps_ts/`）/ JS共有ライブラリ（`vendor/`） |
| **通信と計算の分離** | `ws-client/`（WebSocket 受信、ヘッドレス可）と `voxel/`（座標計算）を分離 |
| **計算と描画の分離** | `voxel/`（座標計算、ヘッドレス可）と `viewer/`（Three.js 描画）を分離 |
| **判定と表示の分離** | `detector/`（侵入判定、ヘッドレス可）と `viewer/overlays/`（ハイライト表示）を分離 |
| **通信層の独立** | `ws-client/`（WS受信）と `mqtt-client/`（MQTT通信）は独立した通信ライブラリ |
| **依存関係の単方向性** | `apps_ts/ → ws-client/ → (外部)`, `apps_ts/ → viewer/ → voxel/ → vendor/` |
| **ヘッドレス実行可能** | `ws-client/`, `voxel/`, `detector/`, `mqtt-client/` はブラウザなしでサーバーサイド実行可能 |
| **viewer はデータソースを知らない** | viewer は `VoxelSnapshot` を受け取るだけ。WebSocket の存在を知らない |

### A.8 ouster_bridge3 → cepf-sdk 移行マッピング

| ouster_bridge3 の旧ファイル | 移行先 | 備考 |
|---------------------------|-------|------|
| `ouster_to_ws/ouster_to_ws.py` | `cepf_sdk/transport/websocket_server.py` + `cepf_sdk/parsers/ouster.py` | パーサー部分とWebSocket部分を分離 |
| `http_server.py` | `cepf_sdk/transport/http_server.py` | 配信ディレクトリを設定可能に |
| `three/src/voxel.ts`（座標計算部分） | `voxel/src/voxel-grid.ts` | viewer から分離、Three.js 無依存 |
| `three/src/voxel.ts`（描画部分） | `viewer/src/renderers/voxel-renderer.ts` | Three.js InstancedMesh 生成のみ |
| `three/src/index.ts`（WebSocket受信） | `ws-client/src/ws-connection.ts` | ★ viewer から分離、ヘッドレス可 |
| `three/src/index.ts`（Three.jsシーン管理） | `viewer/src/index.ts` | 描画のみ、WS を知らない |
| `three/src/stats.ts` | `viewer/src/stats.ts` | そのまま移動 |
| （新規） | `ws-client/src/point-stream.ts` | マルチソース点群ストリーム |
| （新規） | `voxel/src/spatial-id-converter.ts` | 空間ID変換（vendor/alogs 使用）|
| （新規） | `viewer/src/renderers/spatial-id-renderer.ts` | 空間ID描画 |
| （新規） | `viewer/src/overlays/drone-sprite.ts` | ドローンスプライト表示 |
| （新規） | `viewer/src/overlays/intrusion-highlight.ts` | 侵入ハイライト表示 |
| `three/index.html` | `viewer/index.html` | そのまま移動 |
| `three/styles/` | `viewer/styles/` | そのまま移動 |
| `three/webpack.config.js` | `viewer/webpack.config.js` | 出力先調整 |
| `three/tsconfig.json` | `viewer/tsconfig.json` | 設定継承 |
| `three/package.json` | `viewer/package.json` | voxel/ への依存を設定 |
| `ws/` | （削除） | 空フォルダ、不要 |

---

### A.6 `apps/` フォルダの役割 — なぜ filters は置かないのか？

> **質問**: `apps/processing/filters/` も存在するのに、なぜわざわざ `cepf_sdk/filters/` に集中してもう一度書くのか？

**答え: フィルタ処理は「汎用部品」だからです。`apps/` には「アプリケーション固有のロジック」だけを置きます。**

#### 責任範囲の分離

| レイヤー | 役割 | 例 |
|---------|------|------|
| `cepf_sdk/filters/` | **再利用可能な汎用フィルタ** | CylindricalRangeFilter, StatisticalOutlierRemoval, VoxelDownsample |
| `apps/` | **特定アプリケーション固有のロジック** | パイプライン実行制御、ロギング設定、出力形式決定、結果表示方法 |

#### なぜ分ける？

```
❌ 悪い設計（filters を apps/ に置く）

apps/
├── run_pipeline.py
├── processor.py
└── processing/filters/range_filter.py    ← ここの range_filter を使いたい
                                            別のアプリから使い回すには?
                                            → cepf-sdk/filters/ に複製する?
                                               メンテナンスが二重に...
│
新規プロジェクト B
├── app_b.py
└── processing/filters/range_filter.py    ← 同じ内容をコピーして配置？
                                               これはコード重複！
```

```
✅ 良い設計（filters を cepf_sdk/ に統一）

cepf_sdk/filters/
├── range/
│   └── cylindrical.py      ← 一元管理。全アプリから使える
└── statistical/
    └── ror.py

apps/
├── run_pipeline.py         ← Airy 用パイプラインの制御ロジック
└── processor.py            ← Airy 用の後処理（ロギング、保存等）

新規プロジェクト B
├── app_b.py
└── processors/             ← Ouster 用の後処理

# どちらのアプリも同じフィルタを使う
from cepf_sdk.filters.range import CylindricalRangeFilter
```

#### 具体例：「アプリケーション固有」とは何か？

**cepf_sdk/filters/ に入るもの:**
```python
# 汎用フィルタ — 何度も再利用される
class CylindricalRangeFilter(PointFilter):
    """どのアプリケーションからも使える汎用フィルタ"""
    def filter(self, points: CepfPoints) -> FilterResult:
        # 円筒領域カットロジック
        pass
```

**apps/processor.py に入るもの:**
```python
# アプリケーション固有の後処理
def processor_loop(q: queue.Queue, config: ProcessorConfig):
    """
    Airy sensor からのパイプラインで、
    特定のロギング形式やファイル保存方法を定義する
    """
    while True:
        frame = q.get()
        
        # ← このアプリケーション固有の選択肢が here
        # 例1: Airy 用のメモリ効率的な出力形式で保存
        # 例2: センサのキャリブレーション情報をログに含める
        # 例3: 特定の可視化フレームワーク用に座標を変換
        
        # でも「フィルタ処理」は cepf_sdk/filters から呼ぶ
        filtered = CylindricalRangeFilter(...).filter(frame.points)
```

#### 移行パス（現在の状態 → 新設計）

**現在：**
```
apps/processing/filters/range_filter.py
  └── CylindricalRangeFilter（Airy 用に最適化）
```

**新設計：**
```
cepf_sdk/filters/range/cylindrical.py
  └── CylindricalRangeFilter（全センサ共通、パラメータ化）

# apps/processor.py で使用
from cepf_sdk.filters.range import CylindricalRangeFilter
filtered_frame = CylindricalRangeFilter(radius=10).filter(frame.points)
```

---

### A.7 「委譲」の具体例 — `airy/decoder.py` の実装パターン

> 「`airy/decoder.py` → `parsers/` に委譲」という表現が分かりにくいためにコード例を示します。

#### 背景

- **現在（互換性維持前）**: `cepf_sdk/airy/decoder.py` に `UdpAiryDecoder` クラスがある。ユーザーのコード（`apps/run_pipeline.py` など）が直接これを使っている。
- **新設計**: パーサーロジックを `cepf_sdk/parsers/robosense_airy.py` の `RobosenseAiryParser` に移す。
- **問題**: 既存ユーザーコードを壊したくない。`from cepf_sdk.airy import UdpAiryDecoder` は引き続き動作してほしい。

#### 解決策：「委譲」パターン

**新しい `cepf_sdk/airy/decoder.py`:**

```python
"""
後方互換ラッパー。新規コードは parsers/robosense_airy.py を直接使用してください。
このモジュールは既存コードの互換性維持のためだけに存在します。
"""

from cepf_sdk.parsers.robosense_airy import RobosenseAiryParser, RobosenseAiryConfig

# 既存の型エイリアスを保持（互換性）
AiryDecodeConfig = RobosenseAiryConfig


class UdpAiryDecoder:
    """
    旧インターフェース（非推奨）。
    
    新規実装は `cepf_sdk.parsers.robosense_airy.RobosenseAiryParser` を使用してください。
    このクラスは内部で Parser に処理を委譲し、既存コードの互換性のみ維持します。
    """
    
    def __init__(self, config: AiryDecodeConfig):
        """
        既存の config を受け取り、新しい Parser に読み替える
        """
        # 内部で新しいパーサーを使う
        self._parser = RobosenseAiryParser(config)
    
    def frames(self):
        """
        既存メソッドを保持。内部では Parser.frames() に委譲
        
        Yields:
            CepfFrame: フレームデータ
        """
        # 実質的には parser.frames() の結果をそのまま返す
        return self._parser.frames()
```

#### 何が起こるか？

**既存ユーザーコードはそのまま動作**

```python
# apps/run_pipeline.py（既存のコード）
from cepf_sdk.airy import UdpAiryDecoder, AiryDecodeConfig

cfg = AiryDecodeConfig(port=6699)
decoder = UdpAiryDecoder(cfg)          # ← 旧インターフェース、動作する！

for frame in decoder.frames():         # ← 内部で新しいパーサーが動いている
    print(frame.point_count)
```

**新規実装は新しいパーサーを直接使用**

```python
# 新規アプリケーション（推奨）
from cepf_sdk.parsers.robosense_airy import RobosenseAiryParser, RobosenseAiryConfig

cfg = RobosenseAiryConfig(port=6699)
parser = RobosenseAiryParser(cfg)      # ← 新インターフェース

for frame in parser.frames():
    print(frame.point_count)
```

#### 図解：「委譲」のデータフロー

```
既存コード                  airy/decoder.py (互換ラッパー)        新実装
                          ┌──────────────────────────┐
                          │  UdpAiryDecoder          │
                          │  （古い名前を保持）       │
from cepf_sdk.airy    ──→ │   ↓                      │
import UdpAiryDecoder      │   内部で:                │
                          │   _parser =              │
decoder = UdpAiryDecoder()→│    RobosenseAiryParser()├──→ parsers/robosense_airy.py
                          │   ↓                      │    RobosenseAiryParser
decoder.frames()      ──→ │ return                   │    （新しい実装）
                          │ self._parser.frames()    │
                          │                          │
                          └──────────────────────────┘
                                 │
                                 ↓ 実質的には Parser に処理されている
                            CepfFrame が返される
```

#### メリット

| メリット | 説明 |
|---------|------|
| **既存互換性** | 古いユーザーコードは何も変えずに動く |
| **段階的移行** | ユーザーが新しい API に切り替える時間がある |
| **コードの整理** | パーサーロジックが `parsers/` に一元化される |
| **テスト** | 新パーサーだけテストすればよく、互換ラッパーはテスト最小化 |

---

### A.10 侵入検知・MQTT・ドローン表示・TSアプリケーション層の設計

> **背景**: viewer/ とは別に、ボクセルベースの侵入検知ロジック、MQTT 通信、ドローンテレメトリー表示、TypeScript 側のアプリケーションエントリーポイントが必要。

---

#### Q10. 背景ボクセル記憶＋侵入検知を viewer/ と別のフォルダにできないか？

**A: `voxel/` に背景データ構造、`detector/` に判定ポリシーを分離する。**

背景ボクセルマップは「履歴付きボクセルグリッド」— ボクセルの概念。
侵入判定は「差分を閾値で判断する」— ポリシーの概念。これらは別の責任。

| パッケージ | 責任 | キーワード |
|-----------|------|-----------|
| **voxel/** | 「何が変わったか」（データ） | BackgroundVoxelMap, computeDiff |
| **detector/** | 「それは侵入か？」（ポリシー） | IntrusionDetector, ThresholdStrategy |
| **viewer/** | 「結果をどう見せるか」（表示） | IntrusionHighlight |

```
voxel/src/                               # ボクセルデータ構造（背景含む）
├── voxel-grid.ts                        #   リアルタイムボクセルグリッド
├── background-voxel-map.ts              #   背景ボクセルマップ（蓄積・学習）
├── voxel-diff.ts                        #   スナップショット差分計算
├── spatial-id-converter.ts              #   空間ID変換
└── types.ts                             #   VoxelKey, BackgroundStats, VoxelDiffEntry 等

detector/src/                            # 侵入判定ポリシー
├── intrusion-detector.ts                #   VoxelDiff → IntrusionEvent 変換
├── threshold/                           #   閾値アルゴリズム群
│   ├── base.ts                          #   ThresholdStrategy 抽象
│   ├── static.ts                        #   固定閾値
│   ├── adaptive-mean.ts                 #   適応的平均ベース
│   └── adaptive-stddev.ts              #   適応的標準偏差ベース
└── types.ts                             #   IntrusionEvent 型
```

**核心アルゴリズムの概要:**

```typescript
// ── voxel/ 側：データ構造と差分計算 ──

// voxel/src/background-voxel-map.ts
import { VoxelSnapshot, VoxelKey, BackgroundStats } from './types';

export class BackgroundVoxelMap {
  private stats = new Map<VoxelKey, BackgroundStats>();

  /** 学習フェーズ: 各フレームを取り込んで移動平均を更新 */
  learn(snapshot: VoxelSnapshot): void { ... }

  /** 指定キーの背景統計を取得 */
  get(key: VoxelKey): BackgroundStats | undefined { ... }

  /** 学習フレーム数が閾値を超えたか（安定判定） */
  isStable(minSamples: number): boolean { ... }
}

// voxel/src/voxel-diff.ts
import { VoxelSnapshot, VoxelDiffEntry } from './types';
import { BackgroundVoxelMap } from './background-voxel-map';

/** 「何が変わったか」を算出 — 純粋なデータ操作 */
export function computeDiff(
  current: VoxelSnapshot,
  background: BackgroundVoxelMap
): VoxelDiffEntry[] {
  const diffs: VoxelDiffEntry[] = [];
  for (const [key, state] of current) {
    const bg = background.get(key);
    const bgMean = bg?.mean ?? 0;
    diffs.push({
      key,
      currentCount: state.count,
      backgroundMean: bgMean,
      delta: state.count - bgMean,
    });
  }
  return diffs;
}

// ── detector/ 側：ポリシー判定のみ ──

// detector/src/threshold/adaptive-stddev.ts
export class AdaptiveStddevThreshold implements ThresholdStrategy {
  constructor(private sigma: number = 2.0) {}

  /** delta が背景の標準偏差 × σ を超えるかで判定 */
  isIntrusion(delta: number, _mean: number, stddev: number): boolean {
    return delta > this.sigma * stddev;
  }
}

// detector/src/intrusion-detector.ts
import { VoxelDiffEntry } from '../../voxel/src/types';
import { ThresholdStrategy } from './threshold/base';

export class IntrusionDetector {
  constructor(private strategy: ThresholdStrategy) {}

  /** voxel/ が出した差分を受け取り、ポリシーで侵入を判定 */
  evaluate(diffs: VoxelDiffEntry[]): IntrusionEvent[] {
    return diffs
      .filter(d => this.strategy.isIntrusion(d.delta, d.backgroundMean, 0))
      .map(d => ({ voxelKey: d.key, delta: d.delta, timestamp: Date.now() }));
  }
}
```

**この分離の利点:**
- `voxel/` だけで背景学習＋差分計算が完結 → **ヘッドレスのボクセル分析ツール**として独立利用可能
- `detector/` は閾値アルゴリズムの入れ替えだけに集中 → **Strategy パターン**で拡張容易
- viewer は detector の結果を**受け取って表示するだけ** → 検知ロジックを一切知らない

---

#### Q11. VIS のドローンテレメトリーを viewer で表示するには？

**A: viewer 内に `overlays/` フォルダを追加。**

ドローン表示は「描画対象の追加」であり、viewer の責任範囲内。

```
viewer/src/
├── overlays/                              # ★ 新設（オーバーレイ表示群）
│   ├── drone-sprite.ts                    #   ドローン位置のスプライト表示
│   └── intrusion-highlight.ts             #   侵入ボクセルのハイライト表示
```

```typescript
// viewer/src/overlays/drone-sprite.ts
import * as THREE from 'three';

export interface DroneTelemetry {
  droneId: string;
  lat: number;
  lng: number;
  alt: number;
  heading: number;    // 機首方位
  speed: number;      // 速度
  timestamp: number;
}

export class DroneOverlay {
  private sprites = new Map<string, THREE.Sprite>();

  /** テレメトリーを受信してスプライト位置を更新 */
  updateDrone(telemetry: DroneTelemetry): void {
    let sprite = this.sprites.get(telemetry.droneId);
    if (!sprite) {
      sprite = this.createDroneSprite(telemetry.droneId);
      this.sprites.set(telemetry.droneId, sprite);
    }
    // 緯度経度 → ローカル座標に変換して配置
    sprite.position.set(
      this.lngToLocal(telemetry.lng),
      this.latToLocal(telemetry.lat),
      telemetry.alt
    );
  }
}
```

---

#### Q12. MQTT ブローカーとのやりとりはどこに？

**A: `mqtt-client/` を新設。viewer からも detector からも使える共有通信ライブラリ。**

MQTT は「通信手段」であり、表示 (viewer) にも検知 (detector) にもアプリ (apps_ts) にも必要。独立が正しい。

```
mqtt-client/                             # ★ 新設（MQTT 通信ライブラリ）
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts                          #   エクスポート
│   ├── mqtt-connection.ts                #   MQTT ブローカー接続管理
│   ├── topics.ts                         #   トピック名定数 + 型定義
│   │                                     #     例: "vis/drone/{id}/telemetry"
│   │                                     #         "cepf/intrusion/alert"
│   └── handlers/
│       ├── telemetry-handler.ts          #   ドローンテレメトリー受信
│       └── intrusion-publisher.ts        #   侵入検知アラート送信
```

---

#### Q13. TypeScript 側のエントリーポイントは？ Python の `apps/` と分離できるか？

**A: `apps_ts/` を新設。Python 側の `apps/` と完全に分離。**

```
apps_ts/                                 # ★ 新設（TypeScript アプリケーション）
├── package.json
├── tsconfig.json
├── src/
│   ├── main-viewer.ts                    #   viewer 起動エントリーポイント
│   │                                     #     → WebSocket接続 + Three.js シーン初期化
│   │                                     #     → detector の結果を viewer に反映
│   │
│   ├── main-detector.ts                  #   侵入検知デーモン（ヘッドレス）
│   │                                     #     → WebSocket でボクセルデータ受信
│   │                                     #     → detector で侵入判定
│   │                                     #     → MQTT で結果送信
│   │
│   └── main-all.ts                       #   統合エントリーポイント
│                                         #     → viewer + detector + mqtt を全部起動
```

```typescript
// apps_ts/src/main-viewer.ts
import { WsConnection } from '../ws-client/src/ws-connection';
import { VoxelGrid } from '../voxel/src/voxel-grid';
import { ViewerApp } from '../viewer/src/index';
import { DroneOverlay } from '../viewer/src/overlays/drone-sprite';
import { IntrusionHighlight } from '../viewer/src/overlays/intrusion-highlight';
import { MqttConnection } from '../mqtt-client/src/mqtt-connection';
import { TelemetryHandler } from '../mqtt-client/src/handlers/telemetry-handler';

// 1. WebSocket 接続（ws-client/ — ヘッドレス可の通信層）
const ws = new WsConnection({ url: 'ws://192.168.1.100:8765' });

// 2. MQTT 接続
const mqtt = new MqttConnection({ broker: 'ws://vis-server:9001' });
const telemetryHandler = new TelemetryHandler(mqtt);

// 3. ドローンオーバーレイ
const droneOverlay = new DroneOverlay();
telemetryHandler.onTelemetry((t) => droneOverlay.updateDrone(t));

// 4. voxel 計算エンジン（Three.js 無依存）
const voxelGrid = new VoxelGrid(1.0);

// 5. viewer 初期化 (Three.js シーンのみ — WebSocket を知らない)
const viewer = new ViewerApp(document.getElementById('app')!);
const intrusionOverlay = new IntrusionHighlight(viewer.scene);

// 6. ws-client → voxel → viewer の配線
ws.connect();
ws.onMessage((points) => {
  for (const p of points) voxelGrid.addPoint(p.x, p.y, p.z, frameId);
  viewer.updateVoxels(voxelGrid.snapshot());
});

// 7. MQTT で侵入アラートを受信してハイライト表示
mqtt.subscribe('cepf/intrusion/alert', (event) => {
  intrusionOverlay.highlight(event.voxelKeys);
});
```

```typescript
// apps_ts/src/main-detector.ts
import { WsConnection } from '../ws-client/src/ws-connection';
import { VoxelGrid } from '../voxel/src/voxel-grid';
import { BackgroundVoxelMap } from '../voxel/src/background-voxel-map';
import { computeDiff } from '../voxel/src/voxel-diff';
import { IntrusionDetector } from '../detector/src/intrusion-detector';
import { AdaptiveStddevThreshold } from '../detector/src/threshold/adaptive-stddev';
import { MqttConnection } from '../mqtt-client/src/mqtt-connection';
import { IntrusionPublisher } from '../mqtt-client/src/handlers/intrusion-publisher';

// 0. WebSocket + ボクセル計算エンジン（ヘッドレス — Three.js 不要）
const ws = new WsConnection({ url: 'ws://192.168.1.100:8765' });
const voxelGrid = new VoxelGrid(1.0);
ws.connect();

// 1. 背景学習（voxel/ の BackgroundVoxelMap でモデル構築）
const bgMap = new BackgroundVoxelMap();
console.log('背景学習中...');
for await (const points of ws.frames(learningFrames)) {
  for (const p of points) voxelGrid.addPoint(p.x, p.y, p.z, frameId);
  bgMap.learn(voxelGrid.snapshot());
}

// 2. 侵入検知開始（voxel/ が差分を出し、detector/ がポリシーで判定）
const detector = new IntrusionDetector(new AdaptiveStddevThreshold());
const publisher = new IntrusionPublisher(mqtt);

for await (const points of ws.frames()) {
  for (const p of points) voxelGrid.addPoint(p.x, p.y, p.z, frameId);
  const diffs = computeDiff(voxelGrid.snapshot(), bgMap);   // voxel/: 何が変わった？
  const intrusions = detector.evaluate(diffs);                // detector/: 侵入か？
  if (intrusions.length > 0) {
    publisher.publish(intrusions);
    console.log(`侵入検知: ${intrusions.length} ボクセル`);
  }
}
```

---

### A.11 最終フォルダ構成（v2 — 全機能統合版）

```
sass/                                  #  リポジトリルート 名前かえちゃった。
├── pyproject.toml
├── README.md
│
├── docs/
│
│   ╔══════════════════════════════════════════════════════════════════╗
│   ║               Python 側                                         ║
│   ╚══════════════════════════════════════════════════════════════════╝
│
├── cepf_sdk/                              # ── CEPF SDK ──
│   ├── __init__.py
│   ├── frame.py / types.py / enums.py / config.py / errors.py / usc.py
│   ├── drivers/                           #   センサ固有バイナリ解析
│   ├── parsers/                           #   センサ → CepfFrame 変換
│   ├── filters/                           #   点群フィルタリング
│   ├── transport/                         #   WebSocket / HTTP 転送
│   ├── utils/                             #   座標変換等ユーティリティ
│   └── airy/                              #   後方互換ラッパー
│
├── apps_py/                                  # ── Python アプリケーション ──
│   ├── run_pipeline.py                    #   Airy パイプライン　エントリーポイント
│   └── processor.py                       #   後段処理
│
│   ╔══════════════════════════════════════════════════════════════════╗
│   ║               TypeScript 側                                      ║
│   ╚══════════════════════════════════════════════════════════════════╝
│
├── vendor/                                # ── 空間ID TS ライブラリ ──
│   ├── alogs/                             #   グリッドID ⇔ 緯度経度
│   ├── models/                            #   IGrid, ILatLng 型定義
│   └── util/                              #   Util, HitTest
│
├── voxel/                                 #  ── ボクセル計算エンジン（ヘッドレス可）──
│   ├── package.json                       #   Three.js 無依存
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                       #   エクスポート
│   │   ├── voxel-grid.ts                  #   リアルタイムボクセルグリッド（現フレーム）
│   │   ├── background-voxel-map.ts        #   背景ボクセルマップ（蓄積・学習）
│   │   ├── voxel-diff.ts                  #   スナップショット差分計算
│   │   ├── spatial-id-converter.ts        #   空間ID変換（vendor/alogs 使用）
│   │   └── types.ts                       #   VoxelKey, VoxelState, VoxelSnapshot, BackgroundStats, VoxelDiffEntry 型
│   └── tests/
│
├── ws-client/                             # ★ 新設 ── WebSocket クライアント（ヘッドレス可）──
│   ├── package.json                       #   ブラウザ / Node.js 両対応
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                       #   エクスポート
│   │   ├── ws-connection.ts               #   接続管理・再接続・切断
│   │   ├── point-stream.ts                #   点群ストリーム（callback / AsyncIterator）
│   │   └── types.ts                       #   PointData, ConnectionConfig 型
│   └── tests/
│
├── viewer/                                # ── 3D ビジュアライザ（描画専用）──
│   ├── package.json                       #   voxel/ への依存を設定
│   ├── src/
│   │   ├── index.ts                       #   Three.js シーン管理（※ WS は ws-client/ に分離）
│   │   ├── renderers/
│   │   │   ├── voxel-renderer.ts          #   voxel/ → InstancedMesh 描画
│   │   │   └── spatial-id-renderer.ts     #   voxel/ → GIS座標描画
│   │   ├── overlays/                      #
│   │   │   ├── drone-sprite.ts            #   ドローンスプライト表示
│   │   │   └── intrusion-highlight.ts     #   侵入ボクセルハイライト
│   │   └── stats.ts
│   └── styles/
│
├── detector/                              #  ── 侵入検知エンジン（ヘッドレス可）──
│   ├── package.json
│   ├── src/
│   │   ├── index.ts
│   │   ├── intrusion-detector.ts          #   侵入判定（voxel/ の差分 + 閾値で判定）
│   │   ├── threshold/                     #   閾値アルゴリズム群
│   │   │   ├── base.ts                    #   ThresholdStrategy 抽象
│   │   │   ├── static.ts                  #   固定閾値
│   │   │   ├── adaptive-mean.ts           #   適応的平均ベース
│   │   │   └── adaptive-stddev.ts         #   適応的標準偏差ベース（動的自動調整）
│   │   └── types.ts                       #   IntrusionEvent 型
│   └── tests/
│
├── mqtt-client/                           #  ── MQTT 通信ライブラリ ──
│   ├── package.json
│   ├── src/
│   │   ├── index.ts
│   │   ├── mqtt-connection.ts             #   ブローカー接続管理
│   │   ├── topics.ts                      #   トピック定数・型定義
│   │   └── handlers/
│   │       ├── telemetry-handler.ts       #   ドローンテレメトリー受信
│   │       └── intrusion-publisher.ts     #   侵入アラート送信
│
├── apps_ts/                               # ★ 新設 ── TypeScript アプリケーション ──
│   ├── package.json
│   ├── src/
│   │   ├── main-viewer.ts                 #   viewer + drone + intrusion 統合起動
│   │   ├── main-detector.ts               #   侵入検知デーモン（ヘッドレス）
│   │   └── main-all.ts                    #   全機能統合エントリーポイント
│
└── tests/                                 # ── Python テスト ──
    ├── test_parsers/
    ├── test_filters/
    ├── test_transport/
    └── test_utils/
```

---

### A.12 TypeScript パッケージ間の依存関係

```
apps_ts/
├── main-viewer.ts ───→ ws-client/     (WebSocket 受信)
│                  ───→ voxel/         (ボクセル計算)
│                  ───→ viewer/        (Three.js 描画)
│                  ───→ mqtt-client/   (ドローンテレメトリー受信)
│                  ───→ detector/      (侵入結果の表示)
│
├── main-detector.ts ──→ ws-client/    (WebSocket 受信)
│                    ──→ voxel/        (ボクセル計算)
│                    ──→ detector/     (侵入検知エンジン)
│                    ──→ mqtt-client/  (アラート送信)
│
└── main-all.ts ───→ 全部
```

```
依存の方向（単方向のみ）:

apps_ts/     →  ws-client/    →  （外部: WebSocket API）
             →  voxel/        →  vendor/
             →  viewer/       →  voxel/
             →  detector/     →  voxel/
             →  mqtt-client/  →  （外部: mqtt.js）

ws-client/   →  （外部依存のみ: WebSocket API）
voxel/       →  vendor/       （空間ID変換時のみ）
viewer/      →  voxel/        （スナップショット描画）
detector/    →  voxel/        （背景ボクセルマップ・侵入判定）
mqtt-client/ →  （外部依存のみ: mqtt.js）
vendor/      →  （独立、依存なし）
```

**ポイント:**
- `ws-client/` と `voxel/` が全 TS パッケージの共通基盤
- `viewer/` は WebSocket を知らない。`VoxelSnapshot` を受け取るだけ
- `apps_ts/` が配線役: `ws-client → voxel → viewer` をつなぐ

---

### A.13 なぜこの分離が正しいか

| パッケージ | 関心 | ヘッドレス？ | 依存 | 単体テスト可能？ |
|-----------|------|:-----------:|------|:---------------:|
| `vendor/` | 地理座標変換 | ○ | なし | ○ |
| `ws-client/` | WebSocket 受信・点群ストリーム | ○ | WebSocket API | ○ |
| `voxel/` | ボクセルグリッド・背景記憶・差分計算 | ○ | vendor (空間ID変換時のみ) | ○ |
| `viewer/` | 3D描画・表示 | × | Three.js, voxel/ | ○ (mock Three.js) |
| `detector/` | 侵入判定ポリシー（閾値戦略） | ○ | voxel/ (VoxelDiffEntry 型) | ○ |
| `mqtt-client/` | MQTT 通信 | ○ | mqtt.js | ○ |
| `apps_ts/` | 統合・起動・配線 | 両方可 | 全パッケージ | △ (統合テスト) |
| `cepf_sdk/` | センサ→点群→転送 | ○ | numpy, etc. | ○ |
| `apps_py/` | Python固有起動 | ○ | cepf_sdk | △ |

**「ヘッドレス可」かどうかが分離の判断基準:**
- `ws-client/` はブラウザでも Node.js でも WebSocket 受信を実行できる
- `detector/` はサーバーサイドで画面なしでも侵入検知を実行できる
- `viewer/` はブラウザでの表示が前提（唯一の Three.js 依存パッケージ）
- `mqtt-client/` はどちらの環境でも使える通信層
- `apps_ts/` がこれらを組み合わせる「接着剤」（配線役）

---
