# CEPF-SDK リファクタリング実装記録

**実施日:** 2026-03-03 〜 2026-03-04
**基準文書:** `repos/cepf-sdk/docs/cepf-sdk-refactoring-guide.md`
**基準仕様:** `repos/cepf-sdk/docs/CEPF_USC_Specification_v1_3.md` (v1.3.0)
**成果物:** `repos/sass/` 以下に新規構築

---

## 実施概要

Airy 単体プロトタイプ (`repos/cepf-sdk/`) を、CEPF/USC 仕様書 v1.3 に準拠した **マルチセンサ対応の汎用 SDK** として `repos/sass/` 以下に再構築した。`repos/cepf-sdk/` と `repos/ouster_bridge3/` のコードを参考にしつつ、一切変更していない。`repos/vendor/` もそのまま使用。

---

## 実装完了状況

リファクタリングガイド (セクション9.1) のチェックリストとの照合結果:

| フェーズ | 状態 | 詳細 |
|---------|------|------|
| Phase 1: 基盤モジュール | **完了** | enums, config, errors, frame, types, __init__, pyproject.toml |
| Phase 2: ドライバー・パーサー基盤 | **完了** | drivers/, parsers/base, robosense_airy, parsers/__init__, airy/後方互換 |
| Phase 3: USC メインクラス | **完了** | forge, forge_multi, add_sensor, register_parser, from_json, fluent API |
| Phase 4: フィルター (13種) | **完了** | range(4), statistical(3), attribute(3), classification(2) + pipeline + base |
| Phase 5: ユーティリティ | **完了** | coordinates, quaternion, io |
| Phase 6: 追加パーサー | **完了** | ouster, ouster_dome128, velodyne/ti_radar/continental(スタブ) |
| Phase 7: テスト | **完了** | 44テスト全PASS (run_tests.py) |
| Phase 8: アプリ層・設定・ドキュメント | **完了** | apps_py/, sensors.example.json, pyproject.toml, v1.4仕様書 |

---

## 実施フェーズと成果

### Phase 1: 基盤モジュール

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/__init__.py` | 公開API再エクスポート (CepfFrame, USC, enums, config, errors) |
| `cepf_sdk/enums.py` | SensorType, CoordinateSystem, CoordinateMode, PointFlag |
| `cepf_sdk/errors.py` | 階層的例外クラス (CEPFError → ParseError/ValidationError/ConfigurationError/SerializationError) |
| `cepf_sdk/config.py` | SensorConfig, Transform (to_matrix, inverse), InstallationInfo |
| `cepf_sdk/types.py` | CepfPoints TypedDict, Float32_1D 等の型エイリアス |
| `cepf_sdk/frame.py` | CepfFrame, CepfMetadata (frozen dataclass) — to_json, from_json, to_binary, from_binary, filter_by_flags, transform_points |

### Phase 2: ドライバー & パーサー基盤

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/drivers/__init__.py` | パッケージマーカー |
| `cepf_sdk/drivers/robosense_airy_driver.py` | Airy パケットデコーダ (decode_packet, validate_packet, AiryPacketData, AiryDriverConfig) — 旧 decoder.py のバイナリ解析部分を移植 |
| `cepf_sdk/parsers/__init__.py` | 遅延インポート付きパーサーレジストリ (_PARSER_MAP, get_parser_class) |
| `cepf_sdk/parsers/base.py` | RawDataParser ABC (parse, validate, _next_frame_id) |
| `cepf_sdk/parsers/robosense_airy.py` | RoboSenseAiryParser — drivers/を使い座標変換+CepfFrame生成、全4 coordinate_mode 対応 |

### Phase 3: USC メインクラス

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/usc.py` | UnifiedSenseCloud — add_sensor, forge (7ステップ), forge_multi (numpy.concatenateマージ), from_json, get_parser, register_parser。全setterはself返却でメソッドチェーン対応 |

### Phase 4: フィルター体系 (13フィルター + base + pipeline)

| カテゴリ | ファイル | フィルター |
|---------|---------|-----------|
| 基盤 | `filters/base.py` | PointFilter ABC, FilterMode (MASK/FLAG), FilterResult |
| 基盤 | `filters/pipeline.py` | FilterPipeline (verbose出力対応) |
| range | `filters/range/cylindrical.py` | CylindricalFilter (radius, z範囲, center offset, invert) |
| range | `filters/range/spherical.py` | SphericalFilter |
| range | `filters/range/box.py` | BoxFilter (AABB) |
| range | `filters/range/polygon.py` | PolygonFilter (ray-castingアルゴリズム) |
| statistical | `filters/statistical/ror.py` | RadiusOutlierRemoval (cKDTree) |
| statistical | `filters/statistical/sor.py` | StatisticalOutlierRemoval (cKDTree) |
| statistical | `filters/statistical/voxel.py` | VoxelDownsample (ハッシュベース) |
| attribute | `filters/attribute/intensity.py` | IntensityFilter (min/max) |
| attribute | `filters/attribute/confidence.py` | ConfidenceFilter (min) |
| attribute | `filters/attribute/flag.py` | FlagFilter (include/exclude bitmask) |
| classification | `filters/classification/ground.py` | GroundClassifier (FLAG mode, GROUND bit) |
| classification | `filters/classification/noise.py` | NoiseClassifier (FLAG mode, NOISE bit, cKDTree) |

### Phase 5: ユーティリティ

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/utils/coordinates.py` | spherical_to_cartesian, cartesian_to_spherical, lla_to_ecef, ecef_to_lla (WGS84, Bowring法) |
| `cepf_sdk/utils/quaternion.py` | quaternion_to_rotation_matrix, rotation_matrix_to_quaternion |
| `cepf_sdk/utils/io.py` | load_cepf_file, save_cepf_file, cepf_to_pcd, cepf_to_las |

### Phase 6: 追加パーサー

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/parsers/ouster.py` | OusterBaseParser, OusterLidarParser — ouster-sdk ラッパー (遅延インポート, XYZLut, parse_scan, open_source_iter) |
| `cepf_sdk/parsers/ouster_dome128.py` | OusterDome128Parser — Dome 128 固有デフォルト設定 |
| `cepf_sdk/parsers/velodyne.py` | VelodyneLidarParser (スタブ、NotImplementedError) |
| `cepf_sdk/parsers/ti_radar.py` | TIRadarParser (スタブ、MAGIC_WORD定義済み) |
| `cepf_sdk/parsers/continental.py` | ContinentalRadarParser (スタブ) |

### Phase 7: テスト

| ファイル | テスト内容 | テスト数 |
|---------|-----------|---------|
| `tests/test_enums.py` | 全列挙型の値、フラグ合成 | 4 |
| `tests/test_frame.py` | frozen制約, to_json/from_json往復, to_binary, filter_by_flags, transform_points | 7 |
| `tests/test_usc.py` | add_sensor+forge, sensor_not_found, validation, forge_multi, get_parser, installation, transform, filter, fluent API, from_json | 10 |
| `tests/test_parsers/test_robosense_airy.py` | driver decode/validate, Airy parse/invalid/coordinate modes/frame_id | 6 |
| `tests/test_parsers/test_ouster.py` | ouster-sdk importガード | 2 |
| `tests/test_filters/test_cylindrical.py` | basic, invert, FLAG mode, center offset | 4 |
| `tests/test_filters/test_ror.py` | outlier除去, 大半径, 空入力 | 3 |
| `tests/test_filters/test_pipeline.py` | empty, single, chained, verbose | 4 |
| `tests/test_utils/test_coordinates.py` | sph↔cart, lla↔ecef 往復 | 4 |
| `run_tests.py` | pytest不要のテストランナー (全44テスト) | — |

**テスト結果: 44 passed, 0 failed** (2026-03-04 最終確認済み)

### Phase 8: アプリケーション層・設定・ドキュメント

| ファイル | 内容 |
|---------|------|
| `cepf_sdk/airy/__init__.py` | 後方互換ラッパー (DeprecationWarning) |
| `cepf_sdk/airy/decoder.py` | UdpAiryDecoder, AiryDecodeConfig → parsers/robosense_airy.py に委譲 |
| `pyproject.toml` | cepf-sdk v0.2.0, deps: numpy/scipy, optional: ouster-sdk/laspy/pytest |
| `apps_py/run_pipeline.py` | パイプラインエントリーポイント (argparse, JSON設定読み込み) |
| `apps_py/processor.py` | FrameProcessor (後段処理ハンドラー管理) |
| `apps_py/sensors.example.json` | センサー設定テンプレート (Airy + Ouster Dome 128 + installation) |
| `.gitignore` | Python + sensors.json除外 + IDE |
| `docs/CEPF_USC_Specification_v1_4.md` | v1.4 完全仕様書 (変更履歴、全セクション更新) |

---

## ファイル数サマリー

| カテゴリ | ファイル数 |
|---------|--------:|
| cepf_sdk/ コア | 7 |
| cepf_sdk/drivers/ | 2 |
| cepf_sdk/parsers/ | 8 |
| cepf_sdk/filters/ | 16 |
| cepf_sdk/utils/ | 4 |
| cepf_sdk/airy/ (後方互換) | 2 |
| tests/ | 12 |
| apps_py/ | 3 |
| 設定・ドキュメント | 4 |
| **合計** | **58** |

---

## 制約の遵守

| 制約 | 遵守状況 |
|------|---------|
| `repos/sass/` 以下のみ編集 | ✓ |
| `repos/cepf-sdk/` 未変更 | ✓ (参照のみ) |
| `repos/ouster_bridge3/` 未変更 | ✓ (参照のみ) |
| `repos/vendor/` 未変更 | ✓ (そのまま使用) |
| cepf_sdk/ のコード再利用 | ✓ (frame.py, types.py, decoder.pyのパターンを移植) |

---

## 実行環境

- **プラットフォーム:** Linux 5.15.148-tegra (Jetson)
- **Python:** 3.10.12
- **numpy:** 1.21.5
- **scipy:** 1.8.0
- **AI:** Claude Opus 4.6 (claude-opus-4-6)

---

## 検証済み環境 (2026-03-04 更新)

| 項目 | 状態 | 備考 |
|------|------|------|
| `pytest` 公式テスト実行 | **完了** | pytest 9.0.2 (pip --user インストール) / **92 passed** |
| ouster-sdk インストール | **完了** | ouster-sdk 0.16.1 (pip --user インストール) |
| Ouster パーサー結合テスト | **完了** | 18テスト追加 / 全92テスト PASS |
| ouster.py v0.16 対応修正 | **完了** | ChanField API 変更 (int→str, `ouster.sdk.client`→`ouster.sdk.core`) に対応 |
| Velodyne パーサー実装 | **完了** | VLP-16 (2 firings/block) / VLP-32C 対応 / 20テスト追加 |
| TI Radar パーサー実装 | **完了** | AWR1843/IWR6843 TLV プロトコル / TLV1+TLV7 / 17テスト追加 |
| **全テスト** | **完了** | **129 passed** (2026-03-04 最終確認) |

---

## 残課題・今後の作業

| 項目 | 優先度 | 備考 |
|------|:------:|------|
| Continental パーサー実装 | 低 | 現在スタブ |
| CI/CD パイプライン構築 | 中 | GitHub Actions 等 |
| TypeScript アプリ層 (apps_ts/) | 低 | 必要に応じて |
