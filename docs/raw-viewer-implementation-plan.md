# Raw Viewer（フィルター前点群プレビュー）実装計画

> **目的:** フィルター処理前の生点群を別タブで表示し、フィルター後の Viewer と並べて比較することで、フィルターのデバッグと効果確認を行う。  
> **作成日:** 2026-03-21  
> **ステータス:** 計画段階  

---

## 1. 要件定義

### 1.1 機能要件

| ID | 要件 | 優先度 |
|----|------|:------:|
| FR-1 | フィルター処理**前**の生点群を Three.js で表示する | 必須 |
| FR-2 | ワイヤーフレーム表示は**不要**（表示しない） | 必須 |
| FR-3 | ボクセル表示は**不要**（表示しない） | 必須 |
| FR-4 | 既存 Viewer（`:3000`）と同じ HTML/バンドルを共用する | 必須 |
| FR-5 | ブラウザの別タブで開く（ポートは同じ `:3000`、URL パラメーターで分岐） | 必須 |
| FR-6 | `./start.sh --raw-viewer` オプションで ON/OFF を切り替える | 必須 |
| FR-7 | OFF 時にパフォーマンス影響が**ゼロ**であること | 必須 |

### 1.2 非機能要件

| ID | 要件 |
|----|------|
| NFR-1 | 既存 Viewer のコード・動作に破壊的変更を加えない |
| NFR-2 | webpack リビルド 1 回で完了する（別バンドル不要） |
| NFR-3 | 追加ポートは WS 用の 1 つのみ（HTTP サーバー追加なし） |

---

## 2. アーキテクチャ設計

### 2.1 全体構成

```
OusterPcapSource / AiryLiveSource
  │
  ├──[--raw-viewer 時のみ]──→ WebSocketTransport(:8766)
  │                               ↓
  │                    http://localhost:3000/?rawPort=8766
  │                    （同一 HTML + bundle.js、点群のみ表示）
  │
  ↓ FilterPipeline
  │
  └──→ WebSocketTransport(:8765) → http://localhost:3000
                                    （既存 Viewer、変更なし）
```

### 2.2 設計判断の根拠

#### Q1. WebSocket サーバーを分けるか同居か？

**→ 分ける（別ポート 8766）。** 理由：

| 比較軸 | 同一サーバー (8765) | **別サーバー (8766) ← 採用** |
|--------|--------------------|-----------------------------|
| OFF 時コスト | `msg.type` 判定が全フレームに走る | `raw_transport is None` → `if` 1 回（ナノ秒） |
| 既存 Viewer 影響 | raw フレーム無視ロジック追加が必要 | 完全無干渉 |
| 帯域効率 | 全クライアントに全メッセージ | 各 WS に繋いだクライアントのみ受信 |
| 実装の単純さ | メッセージ種別の取り決めが必要 | `_process_frame()` を 2 回呼ぶだけ |

#### Q2. HTTP サーバーを分けるか？

**→ 分けない。** 理由：

- 同じ `viewer/index.html` + `dist/bundle.js` を共用
- `?rawPort=8766` URL パラメーターで Raw モードを判別
- `window.location.hostname` で WS ホスト名を自動解決するため、IP アクセスにも対応

```
http://localhost:3000                  ← 既存（フィルター後、ワイヤーフレーム＋ボクセルあり）
http://localhost:3000/?rawPort=8766    ← Raw Viewer（フィルター前、点群のみ）
http://192.168.10.101:3000/?rawPort=8766  ← リモートアクセスも動作
```

#### Q3. Raw Viewer 用の webpack エントリーポイントを分けるか？

**→ 分けない。** 理由：

- `main.ts` 内で `URLSearchParams` による分岐（約 15 行追加）で対応可能
- 別バンドルにすると webpack.config.js のマルチエントリー化 + 別 HTML が必要になり複雑
- `resolveWsUrl()` に前例がある（`?ws=` パラメーターで WS URL を上書き）

---

## 3. 変更ファイル一覧

| # | ファイル | 変更種別 | 変更概要 |
|:-:|---------|:--------:|---------|
| 1 | `apps/run_pipeline.py` | 修正 | `--raw-ws-port` CLI 引数追加、メインループに raw 送信追加 |
| 2 | `viewer/src/main.ts` | 修正 | `?rawPort=` 判定、Raw モード時のレイヤー初期化分岐 |
| 3 | `start.sh` | 修正 | `--raw-viewer` オプション追加、パイプライン起動コマンド拡張 |
| 4 | `docs/readme.md` | 修正 | §3.6 に Raw Viewer 操作マニュアル追加 |

**作成不要なファイル:** なし（既存ファイルの修正のみ）

---

## 4. 詳細設計

### フェーズ 1: Python パイプライン（`apps/run_pipeline.py`）

#### ステップ 1.1: CLI 引数追加

`_build_parser()` の WebSocket 設定グループに追加：

```python
ws.add_argument("--raw-ws-port", type=int, default=None,
                help="フィルター前点群用 WebSocket ポート（未指定時は Raw Viewer 無効）")
```

**設計上の注意:**
- `default=None` により、未指定時は Raw Viewer が完全に無効化される
- `type=int` でバリデーション済み
- `--ws-port` と同じ値が指定された場合のガード処理を入れること

#### ステップ 1.2: Raw WebSocket サーバー起動（条件付き）

`main()` 内、既存の `_start_websocket_server()` 呼び出しの直後に追加：

```python
# 既存
transport, ws_loop = _start_websocket_server(host=args.ws_host, port=args.ws_port)

# 追加（Raw Viewer 用）
raw_transport = None
raw_ws_loop = None
if args.raw_ws_port is not None:
    if args.raw_ws_port == args.ws_port:
        logger.error("--raw-ws-port と --ws-port が同じ値です: %d", args.raw_ws_port)
        sys.exit(1)
    raw_transport, raw_ws_loop = _start_websocket_server(
        host=args.ws_host, port=args.raw_ws_port
    )
    logger.info("Raw Viewer WebSocket: ws://%s:%d", args.ws_host, args.raw_ws_port)
```

**技術的根拠:**
- `_start_websocket_server()` は毎回 `asyncio.new_event_loop()` + 新スレッドを生成するため、複数回呼び出し可能（ポートが異なる限り）
- `WebSocketTransport` インスタンスは独立した `_clients` Set を持ち、相互に干渉しない

#### ステップ 1.3: メインループ修正

```python
for frame in source.frames():
    # ── Raw Viewer 配信（フィルター前） ──
    if raw_transport is not None:
        _process_frame(frame, raw_transport, raw_ws_loop)

    # ── フィルター適用 ──
    filtered = _apply_pipeline(frame, pipeline)

    # ── 既存 Viewer 配信（フィルター後） ──
    _process_frame(filtered, transport, ws_loop)
```

**OFF 時のオーバーヘッド分析:**
- `if raw_transport is not None:` → Python の `None` チェック 1 回（ナノ秒オーダー）
- `_process_frame()` も `if transport is not None` で内部ガードあり
- **結論: パフォーマンス影響は計測不能レベル**

**フレームコピーの不要性:**
- `_apply_pipeline()` は `dataclasses.replace()` を使用 → 元の `frame` オブジェクトは不変
- raw_transport に `frame` を、transport に `filtered` を渡しても安全

#### ステップ 1.4: effective_config の Raw WS への非送信

Raw WebSocket には `filter_config` メッセージを**送信しない**：
- Raw Viewer にワイヤーフレームは不要（FR-2）
- `broadcast_raw()` を `raw_transport` に対して呼ばないだけで自然に実現
- `WebSocketTransport._last_raw` キャッシュも `None` のまま → 新規接続時にも `filter_config` は送信されない

---

### フェーズ 2: Viewer TypeScript（`viewer/src/main.ts`）

#### ステップ 2.1: Raw モード判定

async IIFE の先頭（config.json 読み込みの直後）に追加：

```typescript
// ── Raw Viewer モード判定 ──
const params = new URLSearchParams(window.location.search);
const rawPort = params.get("rawPort");
const rawMode = rawPort !== null;
```

#### ステップ 2.2: WS URL の上書き

```typescript
let WS_URL: string;
if (rawMode) {
  // rawPort パラメーターからポート番号を取得し WS URL を構築
  WS_URL = `ws://${window.location.hostname}:${rawPort}`;
  console.log("[RAW VIEWER] Raw mode enabled, WS:", WS_URL);
} else {
  WS_URL = await resolveWsUrl();
}
```

**`resolveWsUrl()` を修正せずに直接 URL を構築する理由:**
- `?rawPort=` と `?ws=` の 2 つの URLSearchParams が競合する可能性がある
- Raw モード時は `resolveWsUrl()` のフォールバック順序（`?ws=` → `<meta>` → デフォルト）を通す必要がない
- `window.location.hostname` を直接使うことで、リモートアクセス（`192.168.10.101:3000/?rawPort=8766`）でも正しく動作

**→ `ws-client/src/resolve-ws-url.ts` の変更は不要に** （変更ファイル一覧から除外）

#### ステップ 2.3: レイヤー初期化の分岐

既存の `if (voxelMode === "both") { ... } else { ... }` 分岐の**前**に `rawMode` 判定を最優先で挿入する。
`?rawPort=` と `voxel_mode: "both"` の組み合わせは想定外のため、Raw モード時は常にシングル・点群のみモードに強制する。

```typescript
if (rawMode) {
  // ── Raw Viewer 専用パス（常にシングル・点群のみ） ──
  const container = document.getElementById("viewer-container") as HTMLElement;
  if (!container) throw new Error("#viewer-container が見つかりません");

  const viewer     = new ViewerApp(container, config.coin);
  const dispatcher = new FrameDispatcher();

  dispatcher.register(new PointCloudLayer(viewer));
  // ボクセル・ワイヤーフレーム・LayerPanel は登録しない

  conn.onMessage((points) => {
    dispatcher.dispatch(points);
    setStatus("RAW ✓", dispatcher.frameId, points.length);
  });

  viewer.render();
} else if (voxelMode === "both") {
  // 既存スプリットモード（変更なし）
  // ...
} else {
  // 既存シングルモード（変更なし）
  // ...
}
```

#### ステップ 2.4: ステータスバーの表示

Raw モード時のステータス表示を区別する：

```typescript
setStatus(rawMode ? "RAW ✓" : "接続済み ✓", dispatcher.frameId, points.length);
```

**追加考慮: ページタイトル**
```typescript
if (rawMode) {
  document.title = "CEPF Raw Viewer（フィルター前）";
}
```

---

### フェーズ 3: start.sh

#### ステップ 3.1: 変数・オプション追加

```bash
# フラグ（既存のフラグと同じセクションに追加）
RAW_VIEWER_PORT=""

# 引数パース（case 文に追加）
--raw-viewer)  RAW_VIEWER_PORT=8766; shift ;;
```

**ポート 8766 固定の意図:** 現時点では設定可能にする必要がないため、ハードコード。将来 `SASS_RAW_WS_PORT` 環境変数で上書き可能にすることを検討（セクション 10 参照）。

#### ステップ 3.2: パイプライン起動コマンドへの引数追加

ステップ 5 のパイプライン起動部分で、`$PIPELINE_FILTERS` の後に追加：

```bash
# Raw Viewer 引数を構築
RAW_VIEWER_ARG=""
if [ -n "$RAW_VIEWER_PORT" ]; then
    RAW_VIEWER_ARG="--raw-ws-port $RAW_VIEWER_PORT"
fi

# Airy モード / PCAP モードの両方で $RAW_VIEWER_ARG を追加
PYTHONPATH="$SCRIPT_DIR" python3 apps/run_pipeline.py \
    --use-pcap \
    ...
    $PIPELINE_FILTERS \
    $RAW_VIEWER_ARG \
    --verbose
```

**注意:**
- Airy モードの起動コマンドにも同じ `$RAW_VIEWER_ARG` を追加すること（漏れやすいポイント）。
- fallback パス（`pcap_replay.py` を使う簡易モード）は FilterPipeline を通さないため `$RAW_VIEWER_ARG` の追加は**不要**。

#### ステップ 3.3: 起動メッセージ

WebSocket サーバー起動確認後に表示：

```bash
if [ -n "$RAW_VIEWER_PORT" ]; then
    log_info "Raw Viewer: ${GREEN}http://localhost:$HTTP_PORT/?rawPort=$RAW_VIEWER_PORT${NC}"
fi
```

#### ステップ 3.4: ヘルプ表示の更新

start.sh 先頭のコメントに追加：

```bash
#    ./start.sh --raw-viewer     # フィルター前点群プレビュー (Raw Viewer) も起動
```

---

### フェーズ 4: webpack リビルド

```bash
cd viewer && npm run bundle
```

- `main.ts` の変更を `dist/bundle.js` に反映
- 他のファイル（index.html, styles/）は変更不要

---

### フェーズ 5: ドキュメント更新（`docs/readme.md`）

#### §3.6 コマンドラインオプション表に追加

```markdown
| `./start.sh --raw-viewer` | フィルター前点群プレビュー (Raw Viewer) も起動 |
```

#### §3.6 に Raw Viewer 操作マニュアル追加

- 使い方（URL の開き方、ブラウザの並べ方）
- 注意事項（帯域幅の増加、Jetson のメモリ消費）
- ポートは現在 8766 固定（環境変数によるカスタマイズは将来対応、セクション 10 参照）

---

## 5. OFF 時のパフォーマンス影響分析

| 処理箇所 | OFF 時のコスト | 単位 |
|---------|---------------|------|
| `run_pipeline.py`: `if raw_transport is not None:` | None チェック 1 回/フレーム | ~1 ns |
| `run_pipeline.py`: `_start_websocket_server()` 未呼び出し | 0 | — |
| `main.ts`: `const rawPort = params.get("rawPort")` | URLSearchParams 1 回（初期化時のみ） | ~1 µs |
| `main.ts`: `if (rawMode)` 分岐 | bool チェック 1 回（初期化時のみ） | ~1 ns |
| `start.sh`: `if [ -n "$RAW_VIEWER_PORT" ]` | 空文字チェック 1 回 | ~1 µs |
| WebSocket サーバー未起動 | スレッド・event loop 未生成 | 0 |
| **合計** | **計測不能レベル** | **< 1 µs** |

---

## 6. ON 時のリソース影響

| リソース | 増加量 | 根拠 |
|---------|--------|------|
| **メモリ** | +1 スレッド + 1 asyncio event loop + 1 WebSocketTransport | ~2 MB |
| **CPU** | フレームの JSON シリアライズが 2 倍 | `WebSocketTransport._frame_to_json()` が各 WS スレッドで並列実行（~1 ms/フレーム × 2） |
| **帯域幅** | 128ch × ~46,000 点 × ~160 bytes/点 ≈ **7.4 MB/フレーム** を追加配信 | 10 fps 時 ~74 MB/s 追加 |
| **メインループ遅延** | `asyncio.run_coroutine_threadsafe()` 1 回追加（非ブロッキング） | ~数 µs（JSON シリアライズは WS スレッド側で実行されるため、メインループは阻害されない） |

### 帯域幅の軽減策（将来）

- Raw Viewer のブラウザクライアントが接続していない場合、`len(raw_transport._clients) == 0` なら `send()` は即スキップされる（既存の `if not self._clients: return` ガード）
- つまり Raw WS にクライアントが繋がっていなければ、JSON シリアライズも発生しない

---

## 7. エッジケースとガード処理

| # | エッジケース | 対処 |
|:-:|------------|------|
| 1 | `--raw-ws-port` と `--ws-port` が同じ値 | `sys.exit(1)` でエラー終了（ステップ 1.2） |
| 2 | `?rawPort=` に数値以外が入る（`?rawPort=abc`） | WS 接続失敗 → 自動リトライ（既存の `reconnectInterval` で対応） |
| 3 | Raw Viewer タブを開かずに `--raw-viewer` を指定 | `_clients` が空なので `send()` は即 return（帯域消費なし） |
| 4 | `?rawPort=` と `?ws=` を同時指定 | `rawMode` 判定が先 → `?rawPort=` が優先（`resolveWsUrl()` はスキップ） |
| 5 | スプリットモード（`voxel_mode: "both"`）で `?rawPort=` を指定 | `rawMode` が最優先 → 強制シングル・点群のみモード |
| 6 | 既存 Viewer と Raw Viewer のカメラ位置を同期したい | 現時点では非対応。将来は `BroadcastChannel` API や `localStorage` で対応可能 |
| 7 | Raw Viewer で `filter_config` メッセージが届く場合 | Raw WS には `broadcast_raw()` を呼ばないため届かない。万一届いても `conn.onRawMessage` 未登録なので無視される |
| 8 | ファイアウォールでポート 8766 がブロックされている | log_info に URL 表示で気付ける + トラブルシューティングにポート確認を記載 |

---

## 8. 実装順序と検証

### 実装順序

```
フェーズ 1 (Python)
  ├── ステップ 1.1: CLI 引数追加
  ├── ステップ 1.2: Raw WS サーバー起動
  ├── ステップ 1.3: メインループ修正
  └── ステップ 1.4: effective_config 非送信確認
   ↓
フェーズ 2 (TypeScript)
  ├── ステップ 2.1: Raw モード判定
  ├── ステップ 2.2: WS URL 上書き
  ├── ステップ 2.3: レイヤー初期化分岐
  └── ステップ 2.4: ステータスバー・タイトル
   ↓
フェーズ 3 (start.sh)
  ├── ステップ 3.1: 変数・オプション追加
  ├── ステップ 3.2: パイプライン起動引数
  ├── ステップ 3.3: 起動メッセージ
  └── ステップ 3.4: ヘルプ更新
   ↓
フェーズ 4 (webpack リビルド)
  └── cd viewer && npm run bundle
   ↓
フェーズ 5 (ドキュメント)
  └── readme.md 更新
```

### 検証チェックリスト

| # | テスト項目 | 方法 |
|:-:|-----------|------|
| 1 | `./start.sh`（--raw-viewer なし）で既存動作が変わらない | Viewer 表示確認 + ログ確認 |
| 2 | `./start.sh --raw-viewer` で WS :8766 が起動する | `ss -tlnp \| grep 8766` |
| 3 | `http://localhost:3000` でフィルター後点群＋ワイヤーフレーム＋ボクセルが表示される | ブラウザ確認 |
| 4 | `http://localhost:3000/?rawPort=8766` でフィルター前点群のみが表示される | ブラウザ確認 |
| 5 | Raw Viewer でワイヤーフレームが表示されない | 目視確認 |
| 6 | Raw Viewer でボクセルが表示されない | 目視確認 |
| 7 | Raw Viewer のタブタイトルが「CEPF Raw Viewer（フィルター前）」になる | タブ確認 |
| 8 | Raw Viewer の点数 > 既存 Viewer の点数（フィルターで減っているため） | ステータスバー比較 |
| 9 | `http://192.168.10.101:3000/?rawPort=8766` でリモートアクセスが動作する | 別端末から確認 |
| 10 | `--raw-viewer` なしでパイプライン FPS に変化がない | ログの frame 処理間隔を比較 |
| 11 | `--raw-ws-port 8765` で適切にエラーが出る | CLI 実行確認 |
| 12 | `--use-airy-live --raw-viewer` でも動作する | Airy 実機 or ログ確認 |

---

## 9. 変更ファイル最終一覧

| # | ファイル | 変更種別 | 変更行数（概算） |
|:-:|---------|:--------:|:-------:|
| 1 | `apps/run_pipeline.py` | 修正 | +15 行 |
| 2 | `viewer/src/main.ts` | 修正 | +25 行 |
| 3 | `start.sh` | 修正 | +10 行 |
| 4 | `docs/readme.md` | 修正 | +20 行 |
| **合計** | **4 ファイル** | | **~70 行** |

**変更不要と判断したファイル:**

| ファイル | 理由 |
|---------|------|
| `ws-client/src/resolve-ws-url.ts` | Raw モード時は `window.location.hostname` + `rawPort` で直接 URL 構築。`resolveWsUrl()` の変更は不要 |
| `viewer/index.html` | DOM 構造の変更不要。`#viewer-container` をそのまま使用 |
| `viewer/webpack.config.js` | エントリーポイント分割不要。同一 `main.ts` 内で分岐 |
| `viewer/styles/style.css` | Raw モードで追加スタイル不要 |
| `cepf_sdk/transport/websocket_server.py` | 既存の `WebSocketTransport` をそのまま 2 インスタンス稼働 |
| `config/sass.json` | Raw Viewer は config ではなく CLI オプションで制御 |

---

## 10. 将来の拡張（スコープ外）

以下は本計画のスコープには含めないが、将来の検討候補として記録する。

| 拡張案 | 概要 |
|--------|------|
| カメラ同期 | Raw Viewer と既存 Viewer のカメラ位置・角度を `BroadcastChannel` API で同期 |
| 色分け表示 | フィルターで除外された点を赤、残った点を緑で表示する差分ビュー |
| `SASS_RAW_WS_PORT` 環境変数 | `start.sh` で `--raw-viewer` 時のポートを環境変数で変更可能にする |
| フレーム同期マーカー | Raw / Filtered の同一フレームを `frame_id` で一致させ、表示タイミングを揃える |
