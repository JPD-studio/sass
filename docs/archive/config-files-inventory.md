# リポジトリ設定ファイル一覧

SASS リポジトリ内の全設定ファイルのインベントリ。

## ルートレベル

### Python / プロジェクト
- [pyproject.toml](../pyproject.toml) — Python プロジェクト設定 (依存、ビルド設定)
- [sass.code-workspace](../sass.code-workspace) — VS Code ワークスペース設定
- [.gitignore](../.gitignore) — Git 無視ファイル

---

## アプリケーション設定

### Python アプリ (apps/)
- [apps/sensors.example.json](../apps/sensors.example.json) — センサー設定のサンプル

### TypeScript アプリ (apps_ts/)
- [apps_ts/sensors.example.json](../apps_ts/sensors.example.json) — TypeScript アプリのセンサー設定サンプル
- [apps_ts/package.json](../apps_ts/package.json) — npm パッケージ定義
- [apps_ts/tsconfig.json](../apps_ts/tsconfig.json) — TypeScript コンパイラ設定

---

## ライブラリ・モジュール設定

### ws-client
- [ws-client/package.json](../ws-client/package.json)
- [ws-client/tsconfig.json](../ws-client/tsconfig.json)
- [ws-client/jest.config.js](../ws-client/jest.config.js) — Jest テスト設定

### voxel
- [voxel/package.json](../voxel/package.json)
- [voxel/tsconfig.json](../voxel/tsconfig.json)
- [voxel/jest.config.js](../voxel/jest.config.js)

### spatial-grid
- [spatial-grid/package.json](../spatial-grid/package.json)
- [spatial-grid/tsconfig.json](../spatial-grid/tsconfig.json)
- [spatial-grid/jest.config.js](../spatial-grid/jest.config.js)

### detector
- [detector/package.json](../detector/package.json)
- [detector/tsconfig.json](../detector/tsconfig.json)
- [detector/jest.config.js](../detector/jest.config.js)

---

## ビューア/UI 設定

### viewer (Three.js ベースメインビューア)
- [viewer/config.json](../viewer/config.json) — ビューア設定 (WebSocket ホスト/ポート等)
- [viewer/package.json](../viewer/package.json)
- [viewer/tsconfig.json](../viewer/tsconfig.json)
- [viewer/tsconfig.webpack.json](../viewer/tsconfig.webpack.json) — Webpack 用 TypeScript 設定
- [viewer/webpack.config.js](../viewer/webpack.config.js) — Webpack バンドル設定
- [viewer/jest.config.js](../viewer/jest.config.js)

### geo-viewer
- [geo-viewer/config.json](../geo-viewer/config.json) — Geo ビューア設定
- [geo-viewer/package.json](../geo-viewer/package.json)
- [geo-viewer/tsconfig.json](../geo-viewer/tsconfig.json)
- [geo-viewer/tsconfig.webpack.json](../geo-viewer/tsconfig.webpack.json)
- [geo-viewer/webpack.config.js](../geo-viewer/webpack.config.js)
- [geo-viewer/.env.example](../geo-viewer/.env.example) — 環境変数テンプレート

---

## 設定ファイル分類

### JSON 設定
| ファイル | 用途 |
|---------|------|
| `config.json` | アプリケーション固有設定（ポート、接続先等） |
| `sensors*.json` | センサー接続設定 |
| `package.json` | npm 依存定義 |
| `tsconfig.json` | TypeScript コンパイラ設定 |
| `tsconfig.webpack.json` | Webpack ビルド用 TypeScript 設定 |
| `jest.config.js` | Jest テストランナー設定 |

### ビルド・ツール設定
| ファイル | 用途 |
|---------|------|
| `webpack.config.js` | Webpack バンドルの最適化 |
| `pyproject.toml` | Python パッケージング・依存管理 |

### ワークスペース・VCS
| ファイル | 用途 |
|---------|------|
| `*.code-workspace` | VS Code ワークスペース識別 |
| `.gitignore` | Git 追跡除外ルール |
| `.env.example` | 環境変数テンプレート |

---

## 集計

- **JSON 設定**: 23 ファイル
- **JavaScript 設定**: 7 ファイル (jest, webpack)
- **TOML 設定**: 1 ファイル (pyproject.toml)
- **その他**: 3 ファイル (.gitignore, .code-workspace, .env.example)
- **合計**: 34 ファイル

---

## 注記

- `sensors.example.json` は実際の `sensors.json` にコピーして各自編集する想定
- `config.json` ファイル (viewer, geo-viewer) はアプリケーション実行時に参照される
- `.env.example` は環境変数のテンプレート；実際の `.env` は `.gitignore` で保護される
