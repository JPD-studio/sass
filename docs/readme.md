# SASS — センサー統合 SDK 開発ガイド

**プロジェクト:** [JPD-studio/sass](https://github.com/JPD-studio/sass)
**組織:** Japan Process Development Co., Ltd.
**仕様バージョン:** CEPF/USC v1.4.0
**Python:** 3.10+

---

## 目次

1. [プロジェクト概要](#1-プロジェクト概要)
2. [リポジトリ構成](#2-リポジトリ構成)
3. [セットアップ](#3-セットアップ)
4. [アーキテクチャ](#4-アーキテクチャ)
5. [主要コンセプト](#5-主要コンセプト)
6. [対応センサー](#6-対応センサー)
7. [使用例](#7-使用例)
8. [フィルター体系](#8-フィルター体系)
9. [開発ガイド](#9-開発ガイド)
10. [ドキュメント一覧](#10-ドキュメント一覧)

---

## 1. プロジェクト概要

**SASS (Sensor-Agnostic Sensing SDK)** は、LiDAR・Radar 等の複数センサーから取得した点群データを
**CEPF (CubeEarth Point Format)** という統一フォーマットに変換するマルチセンサー対応 Python SDK です。

### 解決する課題

各センサーメーカーはそれぞれ独自のパケットフォーマットと SDK を持っています。
SASS は **UnifiedSenseCloud (USC)** クラスを通じて、センサー差異を吸収し、後段処理（フィルタリング・可視化・記録）を
センサー種別に依存しない共通コードで記述できるようにします。

```
[RoboSense Airy] ──┐
[Ouster Dome 128] ──┤─── USC.forge() ──→ CepfFrame ──→ フィルター ──→ 後段処理
[Velodyne VLP-16] ──┤
[TI AWR1843 Radar]──┘
```

---

## 2. リポジトリ構成

```
sass/
├── cepf_sdk/                    # SDK コア（Python パッケージ）
│   ├── __init__.py              #   公開 API（CepfFrame, USC 等）
│   ├── frame.py                 #   CepfFrame / CepfMetadata データクラス
│   ├── usc.py                   #   UnifiedSenseCloud メインクラス
│   ├── enums.py                 #   SensorType, CoordinateMode 等の列挙型
│   ├── config.py                #   SensorConfig, Transform, InstallationInfo
│   ├── errors.py                #   例外階層
│   ├── types.py                 #   CepfPoints 型エイリアス
│   │
│   ├── drivers/                 #   センサー固有バイナリ解析（CepfFrame を知らない）
│   │   └── robosense_airy_driver.py
│   │
│   ├── parsers/                 #   センサー → CepfFrame 変換
│   │   ├── base.py              #     RawDataParser 抽象基底クラス
│   │   ├── robosense_airy.py    #     RoboSense Airy
│   │   ├── ouster.py            #     Ouster OS シリーズ (ouster-sdk 依存)
│   │   ├── ouster_dome128.py    #     Ouster Dome 128
│   │   ├── velodyne.py          #     Velodyne VLP-16 / VLP-32C
│   │   ├── ti_radar.py          #     TI AWR1843 / IWR6843
│   │   └── continental.py       #     Continental ARS（スタブ）
│   │
│   ├── filters/                 #   点群フィルタリング
│   │   ├── base.py / pipeline.py
│   │   ├── range/               #     領域カット系 (4種)
│   │   ├── statistical/         #     統計系 (3種)
│   │   ├── attribute/           #     属性値系 (3種)
│   │   └── classification/      #     分類系 (2種)
│   │
│   ├── utils/                   #   汎用ユーティリティ
│   │   ├── coordinates.py       #     球面⇔直交, LLA⇔ECEF
│   │   ├── quaternion.py        #     回転行列
│   │   └── io.py                #     CEPF ファイル I/O
│   │
│   └── airy/                    #   後方互換ラッパー（旧 UdpAiryDecoder）
│
├── tests/                       # pytest テスト群（129テスト）
│   ├── test_parsers/
│   ├── test_filters/
│   └── test_utils/
│
├── apps/                        # アプリケーション層
│   ├── run_pipeline.py          #   エントリーポイント
│   ├── processor.py             #   後段処理ハンドラー
│   └── sensors.example.json    #   センサー設定テンプレート
│
├── docs/                        # ドキュメント
│   ├── readme.md                #   ← 本ファイル
│   ├── CEPF_USC_Specification_v1_4.md
│   ├── cepf-sdk-refactoring-guide.md
│   └── implementation-log.md
│
├── vendor/                      # 空間ID TypeScript ライブラリ（変更禁止）
└── pyproject.toml
```

---

## 3. セットアップ

### 3.1 基本インストール

```bash
git clone https://github.com/JPD-studio/sass.git
cd sass
pip install -e .
```

### 3.2 Ouster センサーを使う場合

```bash
pip install -e ".[ouster]"
```

### 3.3 開発環境（テスト込み）

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### 3.4 依存関係

| パッケージ | 用途 | 必須/任意 |
|-----------|------|:--------:|
| numpy | 点群配列演算 | 必須 |
| scipy | KD-tree (ROR/SOR フィルター) | 必須 |
| ouster-sdk >= 0.13 | Ouster センサーパーサー | 任意 |
| laspy | LAS ファイル出力 | 任意 |
| pytest | テスト実行 | 開発時 |

---

## 4. アーキテクチャ

```
┌──────────────────────────────────────────────────────────────┐
│                    UnifiedSenseCloud (USC)                    │
│                                                              │
│  add_sensor(sensor_id, parser_name, config)                  │
│  forge(sensor_id, raw_data)  ──→  CepfFrame                  │
│  forge_multi([...])          ──→  CepfFrame (統合)           │
└──────────────┬───────────────────────────────────────────────┘
               │ パーサーレジストリ経由
       ┌───────┴────────────────────────┐
       │                                │
  RoboSenseAiryParser          OusterLidarParser  ...
       │                                │
  drivers/                       ouster-sdk
  robosense_airy_driver.py      (外部ライブラリ)
       │                                │
       └───────────┬────────────────────┘
                   ↓
              CepfFrame
           ┌──────────────┐
           │ metadata      │  ← センサー種別, 座標系, タイムスタンプ
           │ points        │  ← {x, y, z, intensity, velocity, ...}
           │ extensions    │  ← センサー固有拡張データ
           └──────────────┘
                   ↓
           FilterPipeline
           ├── CylindricalFilter
           ├── RadiusOutlierRemoval
           └── GroundClassifier  ...
```

### レイヤー構造

| レイヤー | 役割 | センサー依存 |
|---------|------|:----------:|
| `drivers/` | バイナリパケット解析 | あり |
| `parsers/` | → CepfFrame 変換 | あり |
| `usc.py` | センサー管理・変換制御 | なし |
| `filters/` | 点群処理 | なし |
| `utils/` | 座標変換・I/O | なし |

---

## 5. 主要コンセプト

### CepfFrame

1フレーム分の点群データを保持する **イミュータブル** なデータクラスです。

```python
from cepf_sdk import CepfFrame, CepfMetadata

frame.format         # "CEPF"
frame.version        # "1.4.0"
frame.metadata       # CepfMetadata (frozen)
frame.points         # {"x": ndarray, "y": ndarray, "z": ndarray, ...}
frame.point_count    # int
frame.extensions     # センサー固有拡張 (dict | None)

# 変換
frame.to_json()      # CEPF JSON 文字列
frame.to_binary()    # CEPF バイナリ
frame.filter_by_flags(include=PointFlag.VALID)
frame.transform_points(transform)
```

### 座標モード (CoordinateMode)

| モード | 含まれるフィールド |
|--------|-----------------|
| `CARTESIAN` | x, y, z |
| `SPHERICAL` | azimuth, elevation, range |
| `BOTH` | x, y, z, azimuth, elevation, range |
| `CARTESIAN_WITH_RANGE` | x, y, z, range |

### PointFlag (ビットフラグ)

| フラグ | 値 | 意味 |
|--------|-----|------|
| `VALID` | 0x0001 | 有効な点 |
| `DYNAMIC` | 0x0002 | 動体 |
| `GROUND` | 0x0004 | 地面（GroundClassifier で付与） |
| `SATURATED` | 0x0008 | 飽和 |
| `NOISE` | 0x0010 | ノイズ（NoiseClassifier で付与） |

---

## 6. 対応センサー

| メーカー | モデル | 種別 | パーサー名 | 状態 |
|---------|--------|------|-----------|:----:|
| RoboSense | Airy | LiDAR | `robosense_airy` | ✅ 実装済み |
| Ouster | OS0/OS1/OS2, Dome 128 | LiDAR | `ouster`, `ouster_dome128` | ✅ 実装済み |
| Velodyne | VLP-16, VLP-32C | LiDAR | `velodyne` | ✅ 実装済み |
| Texas Instruments | AWR1843, IWR6843 | Radar | `ti_radar` | ✅ 実装済み |
| Continental | ARS シリーズ | Radar | `continental` | 🔲 スタブ |

---

## 7. 使用例

### 基本的な変換フロー

```python
from cepf_sdk import UnifiedSenseCloud, SensorConfig, SensorType, CoordinateMode

usc = UnifiedSenseCloud()

# センサー登録
usc.add_sensor(
    sensor_id="front_lidar",
    parser_name="velodyne",
    config=SensorConfig(
        sensor_type=SensorType.LIDAR,
        model="Velodyne VLP-16",
        num_channels=16,
        max_range_m=100.0,
    ),
)

# 変換 (raw_data は UDP パケット bytes)
frame = usc.forge("front_lidar", raw_data, coordinate_mode=CoordinateMode.CARTESIAN)
print(f"点数: {frame.point_count}")
print(f"x[0]: {frame.points['x'][0]:.3f} m")
```

### JSON 設定ファイルから読み込み

```python
usc = UnifiedSenseCloud.from_json("apps/sensors.example.json")
frame = usc.forge("airy_front", raw_data)
```

### 複数センサーの統合

```python
frame_a = usc.forge("lidar_front", raw_a)
frame_b = usc.forge("lidar_rear", raw_b)
merged = usc.forge_multi(["lidar_front", "lidar_rear"], [raw_a, raw_b])
```

### Ouster センサー（LidarScan を使う場合）

```python
from cepf_sdk.parsers.ouster import OusterLidarParser
from cepf_sdk import SensorConfig, SensorType

parser = OusterLidarParser(SensorConfig(
    sensor_type=SensorType.LIDAR,
    model="OS1-128",
))
parser.set_sensor_info(sensor_info)      # ouster_sdk.SensorInfo
frame = parser.parse_scan(lidar_scan)    # ouster_sdk.LidarScan
```

### フィルターパイプライン

```python
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.filters.classification.ground import GroundClassifier

pipeline = FilterPipeline([
    CylindricalFilter(min_radius=0.5, max_radius=50.0, min_z=-2.0, max_z=5.0),
    RadiusOutlierRemoval(radius=0.5, min_neighbors=3),
    GroundClassifier(height_threshold=-1.5),
])

filtered = pipeline.run(frame)
```

---

## 8. フィルター体系

### 8.1 FilterMode

| モード | 動作 |
|--------|------|
| `MASK` | 条件外の点を除去した新フレームを返す |
| `FLAG` | 条件に合う点にビットフラグを付与する |

### 8.2 フィルター一覧

| カテゴリ | クラス | 主なパラメータ |
|---------|--------|-------------|
| **領域カット** | `CylindricalFilter` | min/max_radius, min/max_z, center_x/y, invert |
| | `SphericalFilter` | min/max_range, invert |
| | `BoxFilter` | x/y/z_min, x/y/z_max, invert |
| | `PolygonFilter` | vertices (XY 多角形), invert |
| **統計** | `RadiusOutlierRemoval` | radius, min_neighbors |
| | `StatisticalOutlierRemoval` | k, std_ratio |
| | `VoxelDownsample` | voxel_size |
| **属性値** | `IntensityFilter` | min_intensity, max_intensity |
| | `ConfidenceFilter` | min_confidence |
| | `FlagFilter` | include_flags, exclude_flags |
| **分類** | `GroundClassifier` | height_threshold (FLAG モード) |
| | `NoiseClassifier` | radius, min_neighbors (FLAG モード) |

---

## 9. 開発ガイド

### 9.1 テスト実行

```bash
cd /home/jetson/repos/sass
~/.local/bin/pytest tests/ -v          # 全テスト (129テスト)
~/.local/bin/pytest tests/test_parsers/ -v   # パーサーのみ
```

### 9.2 新しいパーサーを追加する手順

1. **`cepf_sdk/parsers/your_sensor.py`** を作成

```python
from cepf_sdk.parsers.base import RawDataParser
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.enums import CoordinateMode

class YourSensorParser(RawDataParser):
    def validate(self, raw_data: bytes) -> bool:
        return len(raw_data) == EXPECTED_SIZE

    def parse(self, raw_data: bytes,
              coordinate_mode: CoordinateMode | None = None) -> CepfFrame:
        # バイナリ解析 → CepfFrame 生成
        ...
```

2. **`cepf_sdk/parsers/__init__.py`** のレジストリに追加

```python
_PARSER_MAP = {
    ...
    "your_sensor": ("cepf_sdk.parsers.your_sensor", "YourSensorParser"),
}
```

3. **`tests/test_parsers/test_your_sensor.py`** を作成してテストを書く

### 9.3 コミット規約

```bash
git add <files>
git commit -m "feat: add YourSensor parser (VLP-16 mode)"
git push origin main
```

### 9.4 重要な制約

- `vendor/` は **変更禁止**（空間ID TS ライブラリ）
- `CepfFrame` は `frozen=True` のデータクラス — 直接変更不可
- パーサーは `CepfFrame` を返す前に必ず `validate()` を通すこと
- `drivers/` は `CepfFrame` を import しないこと（レイヤー分離の維持）

---

## 10. ドキュメント一覧

| ドキュメント | 内容 |
|------------|------|
| [`docs/CEPF_USC_Specification_v1_4.md`](CEPF_USC_Specification_v1_4.md) | CEPF/USC 完全仕様書（データフォーマット・API 仕様） |
| [`docs/cepf-sdk-refactoring-guide.md`](cepf-sdk-refactoring-guide.md) | アーキテクチャ設計方針・実装ガイド |
| [`docs/implementation-log.md`](implementation-log.md) | 実装履歴・フェーズ別成果物一覧 |
| [`apps/sensors.example.json`](../apps/sensors.example.json) | センサー設定ファイルのテンプレート |

---

*最終更新: 2026-03-04 / CEPF-SDK v0.2.0*
