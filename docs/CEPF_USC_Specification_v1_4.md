# CubeEarth Point Format (CEPF) & UnifiedSenseCloud (USC) 仕様書

**Version:** 1.4.0
**Date:** 2026-03-04
**Author:** Japan Process Development Co., Ltd.
**Status:** Release

---

## 変更履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0.0 | 2025-06-15 | 初版。CEPF JSON形式、基本フィールド定義 |
| 1.1.0 | 2025-08-01 | coordinate_mode 追加、installation 追加、球面座標サポート |
| 1.2.0 | 2025-10-15 | 列指向 (column-oriented) points 構造に変更、timestamp フィールド追加 |
| 1.3.0 | 2026-01-27 | timestamp 算出方法改訂、USC クラス仕様詳細化 |
| 1.4.0 | 2026-03-04 | マルチセンサ対応、パーサーレジストリ、フィルター体系、ドライバー層分離、JSON設定ファイル対応 |

---

## 目次

1. [概要](#1-概要)
2. [用語定義](#2-用語定義)
3. [CEPF データフォーマット仕様](#3-cepf-データフォーマット仕様)
   - 3.1 JSON形式
   - 3.2 バイナリ形式
4. [USC クラス仕様](#4-usc-クラス仕様)
   - 4.1 列挙型
   - 4.2 データクラス
   - 4.3 パーサークラス
   - 4.4 メインクラス
   - 4.5 フィルター体系 (v1.4追加)
   - 4.6 ユーティリティ
5. [データ変換フロー](#5-データ変換フロー)
6. [エラー処理](#6-エラー処理)
7. [拡張ガイドライン](#7-拡張ガイドライン)
8. [付録](#8-付録)

---

## 1. 概要

### 1.1 目的

本仕様書は、LiDARおよびミリ波レーダーからのRAWデータを統一的な点群データに変換するためのデータフォーマット（CEPF）と変換ライブラリ（USC）を定義する。

### 1.2 スコープ

| 項目 | 内容 |
|------|------|
| 入力 | LiDAR/Radar RAWデータ（UDP/シリアル/ouster-sdk LidarScan） |
| 出力 | CEPF形式（JSON/バイナリ） |
| 対象言語 | Python 3.10以上 |
| 依存ライブラリ | numpy, scipy, dataclasses (標準), struct (標準), json (標準) |
| オプション依存 | ouster-sdk>=0.13 (Ousterセンサ用), laspy (LAS出力用) |

### 1.3 命名規則

| 名称 | 正式名 | 用途 |
|------|--------|------|
| **CEPF** | CubeEarth Point Format | データフォーマット名 |
| **USC** | UnifiedSenseCloud | 変換ライブラリ/ファクトリークラス名 |

### 1.4 v1.4 での主な変更点

| 項目 | v1.3 | v1.4 |
|------|------|------|
| アーキテクチャ | Airy単体 | マルチセンサ対応ファクトリーパターン |
| パーサー管理 | なし | 遅延インポート付きレジストリ |
| フィルター | apps/ 内に散在 | 体系的なフィルター階層 (range/statistical/attribute/classification) |
| ドライバー層 | パーサーと混在 | 分離 (drivers/ + parsers/) |
| 設定 | ハードコード | JSON設定ファイル対応 (from_json) |
| エラー処理 | 独自例外なし | 階層的例外クラス |

---

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| RAWデータ | センサーから出力される未加工のバイト列 |
| 点群 (Point Cloud) | 3次元空間上の点の集合 |
| フレーム | 1回のスキャン/検出サイクルで得られる点群データの単位 |
| チャンネル | LiDARの個別レーザー番号 |
| TLV | Type-Length-Value形式のデータ構造 |
| ドップラー速度 | 物体の視線方向相対速度 |
| RCS | Radar Cross Section（レーダー断面積） |
| SNR | Signal-to-Noise Ratio（信号対雑音比） |
| ドライバー | センサ固有のバイナリ解析ロジック。CepfFrame を知らない最下層 |
| パーサー | ドライバー（または外部SDK）を呼び出し、CepfFrame に変換するアダプタ層 |

---

## 3. CEPF データフォーマット仕様

### 3.1 JSON形式

#### 3.1.1 全体構造

```json
{
  "format": "CEPF",
  "version": "1.4.0",
  "metadata": {},
  "schema": {},
  "points": {},
  "point_count": 0,
  "extensions": null
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|:----:|------|
| format | string | ✓ | "CEPF" 固定 |
| version | string | ✓ | セマンティックバージョン |
| metadata | object | ✓ | メタデータオブジェクト |
| schema | object | ✓ | フィールド定義 |
| points | object | ✓ | 列指向の点データ |
| point_count | integer | ✓ | 総点数 |
| extensions | object\|null | - | センサー固有拡張データ |

#### 3.1.2 metadata オブジェクト

```json
{
  "timestamp_utc": "2026-03-04T12:00:00.000000Z",
  "frame_id": 12345,
  "sensor": {},
  "coordinate_system": "sensor_local",
  "coordinate_mode": "cartesian",
  "transform_to_world": null,
  "units": {},
  "installation": null,
  "extra": null
}
```

#### 3.1.3 metadata.sensor オブジェクト

```json
{
  "type": "lidar",
  "model": "RoboSense Airy",
  "serial": "SN123456",
  "firmware": "2.4.0"
}
```

#### 3.1.4 metadata.coordinate_system 値

| 値 | 説明 |
|----|------|
| `"sensor_local"` | センサーローカル座標（デフォルト） |
| `"vehicle_body"` | 車体座標系（前方X、左方Y、上方Z） |
| `"world_enu"` | 東北上座標系 |
| `"world_ecef"` | 地心座標系 |

#### 3.1.5 metadata.transform_to_world オブジェクト

```json
{
  "translation": [0.0, 0.0, 1.5],
  "rotation_quaternion": [1.0, 0.0, 0.0, 0.0]
}
```

クォータニオンの並び順は `[w, x, y, z]`、正規化済み。

#### 3.1.6 metadata.units オブジェクト

```json
{
  "position": "meters",
  "velocity": "m/s",
  "angle": "degrees",
  "intensity": "normalized"
}
```

#### 3.1.7 metadata.installation オブジェクト (v1.1追加)

```json
{
  "reference_point": {
    "description": "drone_port_landing_stage_center",
    "latitude": 34.856789,
    "longitude": 135.678901,
    "altitude": 45.2,
    "datum": "WGS84"
  },
  "sensor_offset_from_reference": {
    "description": "lidar_optical_center_from_landing_stage",
    "offset_x": 0.0,
    "offset_y": 0.0,
    "offset_z": 2.5
  }
}
```

#### 3.1.8 metadata.coordinate_mode 値 (v1.1追加)

| 値 | 説明 | 含まれるフィールド |
|----|------|-------------------|
| `"cartesian"` | 直交座標のみ（デフォルト） | x, y, z |
| `"spherical"` | 球面座標のみ | azimuth, elevation, range |
| `"both"` | 直交座標と球面座標の両方 | x, y, z, azimuth, elevation, range |
| `"cartesian_with_range"` | 直交座標＋距離 | x, y, z, range |

#### 3.1.9 schema オブジェクト

```json
{
  "fields": ["x", "y", "z", "timestamp", "intensity", "confidence", "flags"],
  "types": ["f32", "f32", "f32", "f64", "f32", "f32", "u16"]
}
```

**標準フィールド定義:**

| フィールド名 | 型 | 必須 | 説明 | 値域 |
|-------------|-----|:----:|------|------|
| x | f32 | ※1 | X座標 | 任意 (meters) |
| y | f32 | ※1 | Y座標 | 任意 (meters) |
| z | f32 | ※1 | Z座標 | 任意 (meters) |
| azimuth | f32 | ※2 | 方位角 | -180.0 - 180.0 (degrees) |
| elevation | f32 | ※2 | 仰角 | -90.0 - 90.0 (degrees) |
| range | f32 | ※3 | 距離 | 0.0以上 (meters) |
| timestamp | f64 | ✓ | UNIXタイムスタンプ | ナノ秒精度 |
| intensity | f32 | ✓ | 反射強度 | 0.0 - 1.0 (normalized) |
| velocity | f32 | - | ドップラー速度 | 任意 (m/s)、null許容 |
| confidence | f32 | ✓ | 検出信頼度 | 0.0 - 1.0 |
| return_id | u8 | - | マルチリターン番号 | 0 - 255 |
| flags | u16 | ✓ | ビットフラグ | 0x0000 - 0xFFFF |

※1: coordinate_mode が "cartesian", "both", "cartesian_with_range" の場合に必須
※2: coordinate_mode が "spherical", "both" の場合に必須
※3: coordinate_mode が "spherical", "both", "cartesian_with_range" の場合に必須

**型名一覧:**

| 型名 | サイズ | 説明 |
|------|--------|------|
| f32 | 4 bytes | 32bit浮動小数点 |
| f64 | 8 bytes | 64bit浮動小数点 |
| u8 | 1 byte | 8bit符号なし整数 |
| u16 | 2 bytes | 16bit符号なし整数 |
| u32 | 4 bytes | 32bit符号なし整数 |

#### 3.1.10 points オブジェクト (v1.2で列指向に変更)

点群データは列指向（column-oriented）構造で格納する。

```python
points = {
    "x": np.ndarray,         # shape: (N,), dtype: float32
    "y": np.ndarray,         # shape: (N,), dtype: float32
    "z": np.ndarray,         # shape: (N,), dtype: float32
    "timestamp": np.ndarray, # shape: (N,), dtype: float64
    "intensity": np.ndarray, # shape: (N,), dtype: float32
    ...
}
```

#### 3.1.11 extensions オブジェクト

**LiDAR拡張:**
```json
{
  "lidar": {
    "channel_id": [0, 1, 2, ...]
  },
  "airy": {
    "dist_word_u16": [...],
    "dist_raw_u16": [...]
  }
}
```

**Radar拡張:**
```json
{
  "radar": {
    "velocity_mps": [...],
    "snr_db": [...],
    "rcs_dbsm": [...]
  }
}
```

#### 3.1.12 flags ビット定義

| Bit | 名称 | 値 | 説明 |
|-----|------|-----|------|
| 0 | VALID | 0x0001 | 有効な点 |
| 1 | DYNAMIC | 0x0002 | 動的物体由来 |
| 2 | GROUND | 0x0004 | 地面点 |
| 3 | SATURATED | 0x0008 | センサー飽和 |
| 4 | NOISE | 0x0010 | ノイズ点 |
| 5 | RAIN | 0x0020 | 雨滴由来 |
| 6 | MULTIPATH | 0x0040 | マルチパス由来 |
| 7 | LOW_CONFIDENCE | 0x0080 | 低信頼度 |
| 8-11 | CLASSIFICATION | 0x0F00 | 分類ID (0-15) |
| 12-15 | RESERVED | 0xF000 | 将来拡張用 |

### 3.2 バイナリ形式

#### 3.2.1 全体構造

```
+------------------+
| Header (32 bytes)|
+------------------+
| Point Data       |
| (N × M bytes)   |
+------------------+
| Extensions       |
| (可変長, 任意)    |
+------------------+
```

#### 3.2.2 Header 構造 (32 bytes)

| Offset | Size | 型 | フィールド | 説明 |
|--------|------|-----|-----------|------|
| 0 | 4 | char[4] | magic | "CEPF" (ASCII) |
| 4 | 2 | u16 | version_major | メジャーバージョン |
| 6 | 2 | u16 | version_minor | マイナーバージョン |
| 8 | 1 | u8 | sensor_type | 0=Unknown, 1=LiDAR, 2=Radar |
| 9 | 1 | u8 | coordinate_system | 0=sensor_local, 1=vehicle_body, 2=world_enu, 3=world_ecef |
| 10 | 2 | u16 | header_flags | ヘッダーフラグ |
| 12 | 4 | u32 | point_count | 点数 |
| 16 | 8 | u64 | timestamp_ns | UNIXナノ秒タイムスタンプ |
| 24 | 4 | u32 | frame_id | フレームID |
| 28 | 1 | u8 | coordinate_mode | 座標表現形式 |
| 29 | 3 | u8[3] | reserved | 予約 (0x00) |

バイトオーダー: リトルエンディアン (Little Endian)

---

## 4. USC クラス仕様

### 4.1 列挙型

#### 4.1.1 SensorType

```python
class SensorType(Enum):
    UNKNOWN = 0
    LIDAR = 1
    RADAR = 2
```

#### 4.1.2 CoordinateSystem

```python
class CoordinateSystem(str, Enum):
    SENSOR_LOCAL = "sensor_local"
    VEHICLE_BODY = "vehicle_body"
    WORLD_ENU = "world_enu"
    WORLD_ECEF = "world_ecef"
```

#### 4.1.3 CoordinateMode (v1.1追加)

```python
class CoordinateMode(str, Enum):
    CARTESIAN = "cartesian"
    SPHERICAL = "spherical"
    BOTH = "both"
    CARTESIAN_WITH_RANGE = "cartesian_with_range"
```

#### 4.1.4 PointFlag

```python
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

### 4.2 データクラス

#### 4.2.1 SensorConfig

| 属性 | 型 | 必須 | デフォルト | 説明 |
|------|-----|:----:|-----------|------|
| sensor_type | SensorType | ✓ | - | センサー種別 |
| model | str | ✓ | - | センサー型番 |
| serial_number | str | - | "" | シリアル番号 |
| firmware_version | str | - | "" | ファームウェアバージョン |
| num_channels | int | - | 0 | チャンネル数 |
| horizontal_fov_deg | float | - | 360.0 | 水平視野角 |
| vertical_fov_deg | float | - | 45.0 | 垂直視野角 |
| max_range_m | float | - | 200.0 | 最大検出距離 |
| range_resolution_m | float | - | 0.1 | 距離分解能 |
| velocity_resolution_mps | float | - | 0.1 | 速度分解能 |

#### 4.2.2 Transform

座標変換パラメータ。

| 属性 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| translation | ndarray(3) | [0,0,0] | 並進 [x,y,z] (m) |
| rotation_quaternion | ndarray(4) | [1,0,0,0] | クォータニオン [w,x,y,z] |

メソッド:
- `to_matrix()` → 4x4同次変換行列
- `from_matrix(m)` → Transformインスタンス (classmethod)
- `inverse()` → 逆変換

#### 4.2.3 InstallationInfo (v1.1追加)

| 属性 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| reference_description | str | "" | 基準点の説明 |
| reference_latitude | float | 0.0 | 緯度 (WGS84) |
| reference_longitude | float | 0.0 | 経度 (WGS84) |
| reference_altitude | float | 0.0 | 標高 (m) |
| reference_datum | str | "WGS84" | 測地系 |
| sensor_offset | ndarray(3) | [0,0,0] | 基準点からのオフセット (m) |
| sensor_offset_description | str | "" | オフセットの説明 |

#### 4.2.4 CepfMetadata (frozen dataclass)

| 属性 | 型 | 説明 |
|------|-----|------|
| timestamp_utc | str | ISO 8601形式タイムスタンプ |
| frame_id | int | フレーム連番 |
| coordinate_system | str | 座標系識別子 |
| coordinate_mode | str | 座標表現形式 |
| units | dict | 単位定義 |
| sensor | dict\|None | センサー情報 |
| transform_to_world | dict\|None | ワールド変換情報 |
| installation | dict\|None | 設置情報 |
| extra | dict\|None | 追加メタデータ |

#### 4.2.5 CepfFrame (frozen dataclass)

| 属性 | 型 | 説明 |
|------|-----|------|
| format | str | "CEPF" 固定 |
| version | str | バージョン文字列 |
| metadata | CepfMetadata | メタデータ |
| schema | dict | フィールド定義 |
| points | CepfPoints | 列指向の点群データ |
| point_count | int | 総点数 |
| extensions | dict\|None | 拡張データ |

メソッド:
- `to_numpy()` → Dict[str, ndarray]
- `to_json(indent=2)` → str
- `to_binary()` → bytes
- `from_json(json_str)` → CepfFrame (classmethod)
- `from_binary(data)` → CepfFrame (classmethod)
- `filter_by_flags(include=0, exclude=0)` → CepfFrame
- `transform_points(transform)` → CepfFrame

### 4.3 パーサークラス

#### 4.3.1 RawDataParser (ABC)

全パーサーの抽象基底クラス。

```python
class RawDataParser(ABC):
    def __init__(self, config: SensorConfig): ...
    def _next_frame_id(self) -> int: ...
    def set_default_coordinate_mode(self, mode: CoordinateMode) -> RawDataParser: ...

    @abstractmethod
    def parse(self, raw_data: bytes, coordinate_mode=None) -> CepfFrame: ...

    @abstractmethod
    def validate(self, raw_data: bytes) -> bool: ...
```

#### 4.3.2 パーサー登録マップ (v1.4追加)

```python
_PARSER_MAP = {
    "robosense_airy":  "cepf_sdk.parsers.robosense_airy.RoboSenseAiryParser",
    "ouster_dome128":  "cepf_sdk.parsers.ouster_dome128.OusterDome128Parser",
    "ouster":          "cepf_sdk.parsers.ouster.OusterLidarParser",
    "velodyne":        "cepf_sdk.parsers.velodyne.VelodyneLidarParser",
    "ti_radar":        "cepf_sdk.parsers.ti_radar.TIRadarParser",
    "continental":     "cepf_sdk.parsers.continental.ContinentalRadarParser",
}
```

遅延インポートにより、使用しないパーサーの依存パッケージがなくても動作する。

#### 4.3.3 対応センサー一覧

| メーカー | 型番 | 種別 | パーサー名 | 状態 |
|---------|------|------|-----------|------|
| RoboSense | Airy | LiDAR | robosense_airy | 実装済み |
| Ouster | Dome 128 | LiDAR | ouster_dome128 | 実装済み |
| Ouster | OS0/OS1/OS2 | LiDAR | ouster | 実装済み |
| Velodyne | VLP/HDL | LiDAR | velodyne | スタブ |
| Texas Instruments | AWR/IWR | Radar | ti_radar | スタブ |
| Continental | ARS | Radar | continental | スタブ |

#### 4.3.4 ドライバー層 (v1.4追加)

Airy のようにメーカー公式SDKがないセンサーは、`drivers/` にバイナリ解析ロジックを置く。

```
drivers/robosense_airy_driver.py
  ├── decode_packet(pkt, config) → AiryPacketData
  └── validate_packet(pkt) → bool
```

Ouster のように公式SDK (`ouster-sdk`) があるセンサーは `drivers/` は不要。

### 4.4 メインクラス: UnifiedSenseCloud (v1.4追加)

#### 4.4.1 概要

USC は「翻訳事務所」として、各センサの生データを受け取り、適切なパーサーに解読を依頼し、統一フォーマット (CepfFrame) として返す。

#### 4.4.2 クラス属性

| 属性 | 型 | 説明 |
|------|-----|------|
| _custom_parsers | dict[str, type] | カスタム登録パーサー |

#### 4.4.3 インスタンス属性

| 属性 | 型 | 説明 |
|------|-----|------|
| _parsers | dict[str, RawDataParser] | sensor_id → パーサーインスタンス |
| _transform | Transform | 出力座標変換 |
| _filters | list[Callable] | フィルターチェーン |
| _output_coordinate | CoordinateSystem | 出力座標系 |
| _output_coordinate_mode | CoordinateMode | 出力座標表現形式 |
| _installation | InstallationInfo\|None | 設置情報 |

#### 4.4.4 メソッド一覧

| メソッド | 引数 | 戻り値 | 説明 |
|---------|------|--------|------|
| `register_parser(name, cls)` | str, type | None | カスタムパーサー登録 (classmethod) |
| `from_json(config_path)` | str | USC | JSON設定から初期化 (classmethod) |
| `add_sensor(id, parser_name, config)` | str, str, SensorConfig | self | センサー追加 |
| `set_transform(translation, rotation_quat)` | list[3], list[4] | self | 座標変換設定 |
| `set_output_coordinate(coord_sys)` | CoordinateSystem | self | 出力座標系設定 |
| `set_output_coordinate_mode(mode)` | CoordinateMode | self | 出力座標形式設定 |
| `set_installation(info)` | InstallationInfo | self | 設置情報設定 |
| `add_filter(func)` | Callable | self | フィルター追加 |
| `forge(sensor_id, raw_data, coord_mode)` | str, Any, CoordinateMode\|None | CepfFrame | 単一センサー変換 |
| `forge_multi(data_dict, coord_mode)` | dict, CoordinateMode\|None | CepfFrame | 複数センサー統合変換 |
| `get_parser(sensor_id)` | str | RawDataParser\|None | パーサー取得 |

全 setter メソッドは `self` を返し、メソッドチェーンが可能。

#### 4.4.5 forge() 内部処理フロー

```
forge(sensor_id, raw_data)
  ① sensor_id → パーサーを特定
  ② validate(raw_data) — バイトデータの場合のみ
  ③ parse(raw_data, coordinate_mode) → CepfFrame
  ④ (reserved)
  ⑤ installation 情報を付与（設定されていれば）
  ⑥ Transform 適用（SENSOR_LOCAL 以外の場合）
  ⑦ フィルターを順次適用
  → CepfFrame を返却
```

#### 4.4.6 forge_multi() 内部処理フロー

1. 各 sensor_id に対し forge() を実行
2. 全フレームの points を numpy.concatenate でマージ
3. extensions をセンサー種別ごとに統合
4. 基準フレーム（最初のフレーム）のメタデータをベースに統合 CepfFrame を構築

#### 4.4.7 JSON 設定ファイル形式 (v1.4追加)

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
    "reference_altitude": 220.5,
    "reference_datum": "WGS84",
    "sensor_offset": [1.5, 0.2, 0.3],
    "sensor_offset_description": "屋上コンクリート基準点からの相対位置"
  }
}
```

### 4.5 フィルター体系 (v1.4追加)

#### 4.5.1 基底クラス: PointFilter

```python
class FilterMode(Enum):
    MASK = "mask"   # 点を削除する
    FLAG = "flag"   # flags にビットを立てる（点は残す）

class PointFilter(ABC):
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    @abstractmethod
    def compute_mask(self, points: CepfPoints) -> np.ndarray: ...

    def apply(self, points: CepfPoints) -> FilterResult: ...
```

サブクラスは `compute_mask()` のみ実装すればよい。MASK/FLAG 切り替えは基底クラスが自動対応。

#### 4.5.2 フィルター一覧

**領域カット系 (filters/range/):**

| フィルター | パラメータ | 説明 |
|-----------|-----------|------|
| CylindricalFilter | radius_m, z_min_m, z_max_m, cx, cy, invert | 円筒形 |
| SphericalFilter | radius_m, cx, cy, cz, invert | 球形 |
| BoxFilter | x_min/max, y_min/max, z_min/max, invert | 直方体 |
| PolygonFilter | polygon, z_min, z_max, invert | 多角形柱 |

**統計系 (filters/statistical/):**

| フィルター | パラメータ | 説明 |
|-----------|-----------|------|
| RadiusOutlierRemoval | radius_m, min_neighbors | 半径外れ値除去 (cKDTree使用) |
| StatisticalOutlierRemoval | k_neighbors, std_ratio | 統計外れ値除去 |
| VoxelDownsample | voxel_size | ボクセルダウンサンプリング |

**属性値ベース (filters/attribute/):**

| フィルター | パラメータ | 説明 |
|-----------|-----------|------|
| IntensityFilter | min_intensity, max_intensity | 強度フィルタ |
| ConfidenceFilter | min_confidence | 信頼度フィルタ |
| FlagFilter | include_flags, exclude_flags | フラグフィルタ |

**分類 (filters/classification/):**

| フィルター | パラメータ | 説明 |
|-----------|-----------|------|
| GroundClassifier | z_threshold | 地面検出 (FLAG mode, GROUND bit) |
| NoiseClassifier | min_neighbors, radius_m | ノイズ検出 (FLAG mode, NOISE bit) |

#### 4.5.3 FilterPipeline

```python
pipeline = FilterPipeline(
    filters=[
        CylindricalFilter(radius_m=50.0, z_min_m=-2.0, z_max_m=30.0),
        RadiusOutlierRemoval(radius_m=0.5, min_neighbors=5),
    ],
    verbose=True,
)
result = pipeline.apply(points)
```

### 4.6 ユーティリティ

#### 4.6.1 座標変換 (utils/coordinates.py)

- `spherical_to_cartesian(range_m, azimuth_deg, elevation_deg)` → (x, y, z)
- `cartesian_to_spherical(x, y, z)` → (range_m, azimuth_deg, elevation_deg)
- `lla_to_ecef(lat, lon, alt)` → (x, y, z) [WGS84]
- `ecef_to_lla(x, y, z)` → (lat, lon, alt) [WGS84]

#### 4.6.2 クォータニオン (utils/quaternion.py)

- `quaternion_to_rotation_matrix(q)` → 3x3 ndarray
- `rotation_matrix_to_quaternion(R)` → ndarray(4)

#### 4.6.3 I/O (utils/io.py)

- `load_cepf_file(path)` → CepfFrame
- `save_cepf_file(path, frame)` → None
- `cepf_to_pcd(frame, path)` → None (PCD形式出力)
- `cepf_to_las(frame, path)` → None (LAS形式出力、要 laspy)

---

## 5. データ変換フロー

### 5.1 単一センサーフロー

```
センサー RAW データ
    │
    ▼
UnifiedSenseCloud.forge(sensor_id, raw_data)
    │
    ├── ① パーサー特定 (sensor_id → parser)
    ├── ② validate() (パケット検証)
    ├── ③ parse() (バイナリ解析 → CepfFrame)
    ├── ⑤ installation 付与
    ├── ⑥ Transform 適用
    └── ⑦ Filters 適用
    │
    ▼
CepfFrame
```

### 5.2 マルチセンサーフロー

```
sensor_1 raw_data ──→ forge("sensor_1") ──→ CepfFrame_1
sensor_2 raw_data ──→ forge("sensor_2") ──→ CepfFrame_2
                                               │
                                    forge_multi() でマージ
                                               │
                                               ▼
                                        統合 CepfFrame
```

---

## 6. エラー処理

### 6.1 例外階層

```
CEPFError (基底)
├── ParseError
│   ├── InvalidHeaderError
│   ├── InvalidDataError
│   └── ChecksumError
├── ValidationError
├── ConfigurationError
│   ├── SensorNotFoundError
│   └── ParserNotFoundError
└── SerializationError
```

---

## 7. 拡張ガイドライン

### 7.1 新センサーの追加手順

1. `parsers/my_sensor.py` に `RawDataParser` を継承したクラスを作成
2. `parsers/__init__.py` の `_PARSER_MAP` にエントリ追加
3. 必要に応じて `drivers/my_sensor_driver.py` を追加

### 7.2 カスタムパーサーの登録

```python
UnifiedSenseCloud.register_parser("my_sensor", MySensorParser)
```

### 7.3 カスタムフィルターの追加

```python
@dataclass
class MyFilter(PointFilter):
    threshold: float = 1.0
    mode: FilterMode = FilterMode.MASK
    flag_bit: int = 0x0000

    def compute_mask(self, points: CepfPoints) -> np.ndarray:
        return np.asarray(points["x"]) > self.threshold
```

---

## 8. 付録

### 8.1 ディレクトリ構成

```
cepf-sdk/
├── pyproject.toml
├── cepf_sdk/
│   ├── __init__.py
│   ├── frame.py
│   ├── types.py
│   ├── enums.py
│   ├── config.py
│   ├── errors.py
│   ├── usc.py
│   ├── drivers/
│   │   └── robosense_airy_driver.py
│   ├── parsers/
│   │   ├── base.py
│   │   ├── robosense_airy.py
│   │   ├── ouster.py
│   │   ├── ouster_dome128.py
│   │   ├── velodyne.py
│   │   ├── ti_radar.py
│   │   └── continental.py
│   ├── filters/
│   │   ├── base.py
│   │   ├── pipeline.py
│   │   ├── range/ (cylindrical, spherical, box, polygon)
│   │   ├── statistical/ (ror, sor, voxel)
│   │   ├── attribute/ (intensity, confidence, flag)
│   │   └── classification/ (ground, noise)
│   ├── utils/
│   │   ├── coordinates.py
│   │   ├── quaternion.py
│   │   └── io.py
│   └── airy/ (後方互換ラッパー)
└── tests/
```

### 8.2 依存関係

```toml
[project]
dependencies = ["numpy", "scipy"]

[project.optional-dependencies]
ouster = ["ouster-sdk>=0.13"]
io = ["laspy"]
dev = ["pytest", "pytest-cov"]
```

### 8.3 使用例

```python
from cepf_sdk import UnifiedSenseCloud, SensorConfig, SensorType

# JSON設定から初期化
usc = UnifiedSenseCloud.from_json("sensors.json")

# またはプログラムで構築
usc = UnifiedSenseCloud()
usc.add_sensor("lidar_1", "robosense_airy",
    SensorConfig(sensor_type=SensorType.LIDAR, model="RoboSense Airy"))

# 単一センサー変換
frame = usc.forge("lidar_1", raw_bytes)

# 複数センサー統合
frame = usc.forge_multi({
    "lidar_1": lidar_bytes,
    "radar_1": radar_bytes,
})
```
