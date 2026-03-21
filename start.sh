#!/usr/bin/env bash
# =============================================================================
#  SASS (Sensor Analytics & Surveillance System) — 統合起動スクリプト
# =============================================================================
#
#  使い方:
#    ./start.sh                 # デフォルト: PCAP + Viewer スプリット画面
#    ./start.sh --use-airy-live # Airy LiDAR 実機接続モード
#    ./start.sh --no-detector   # Detector なしで起動
#    ./start.sh --no-viewer     # Viewer なしで起動
#    ./start.sh --geo-viewer    # Geo-Viewer も起動
#    ./start.sh --single-view   # Viewer 単画面で起動
#    ./start.sh --install-only  # 依存関係インストールのみ (起動しない)
#    ./start.sh --restart       # 既存プロセスをキルしてクリーン再起動
#    ./start.sh --stop          # 起動中のプロセスを停止
#
#  データフロー:
#    Source (PCAP | LiDAR UDP)
#      ↓  CepfFrame
#    FilterPipeline (Frustum, RoR, CoordinateTransform, ...)
#      ↓  CepfFrame (filtered)
#    WebSocket (ws://0.0.0.0:8765)
#      ├──▶ Viewer     (http://localhost:3000) [Three.js]
#      ├──▶ Geo-Viewer (http://localhost:3001) [CesiumJS]
#      └──▶ Detector   (ヘッドレス侵入検知)
#
#  フィルター制御:
#    SASS_PIPELINE_FILTERS="--test-frustum"         # デフォルト: Frustum 有効
#    SASS_PIPELINE_FILTERS="--test-frustum --test-ror"  # Frustum + RoR
#    SASS_PIPELINE_FILTERS=""                        # フィルターなし
#
# =============================================================================
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
#  定数 / デフォルト設定
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/.logs"

# ソースモード (pcap | airy)
SOURCE_MODE="pcap"

# PCAP リプレイ設定
PCAP_FILE="${SASS_PCAP:-pcap/demo1.pcap}"
PCAP_META="${SASS_PCAP_META:-pcap/demo1.json}"
PCAP_RATE="${SASS_PCAP_RATE:-1.0}"

# Airy 実機設定
AIRY_PORT="${SASS_AIRY_PORT:-6699}"
AIRY_CONFIG="config/sass.json"

# ポート（SASS_WS_PORT 環境変数でオーバーライド可能）
WS_PORT=8765
HTTP_PORT=3000
GEO_HTTP_PORT=3001

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# フラグ
RUN_VIEWER=true
RUN_GEO_VIEWER=false
RUN_DETECTOR=true
INSTALL_ONLY=false
VIEWER_SPLIT=true

# ──────────────────────────────────────────────────────────────────────────────
#  引数パース
# ──────────────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-viewer)      RUN_VIEWER=false;     shift ;;
        --geo-viewer)     RUN_GEO_VIEWER=true;  shift ;;
        --no-detector)    RUN_DETECTOR=false;   shift ;;
        --single-view)    VIEWER_SPLIT=false;   shift ;;
        --use-airy-live)  SOURCE_MODE="airy";   shift ;;
        --install-only)   INSTALL_ONLY=true;    shift ;;
        --restart)
            # 既存プロセスをキルして再起動
            if [[ -d "$PID_DIR" ]]; then
                echo -e "${YELLOW}■ --restart: 既存プロセスを停止しています...${NC}"
                for pidfile in "$PID_DIR"/*.pid; do
                    [[ -f "$pidfile" ]] || continue
                    pid=$(cat "$pidfile")
                    name=$(basename "$pidfile" .pid)
                    if kill -0 "$pid" 2>/dev/null; then
                        kill "$pid" 2>/dev/null || true
                        echo -e "  ${RED}✗${NC} $name (PID $pid) を停止しました"
                    fi
                    rm -f "$pidfile"
                done
                rmdir "$PID_DIR" 2>/dev/null || true
                echo -e "  ${GREEN}✓${NC} クリーンアップ完了。起動を続行します。"
            else
                echo -e "${YELLOW}  既存プロセスはありません。そのまま起動します。${NC}"
            fi
            shift ;;
        --stop)
            "$0" _stop
            exit 0
            ;;
        _stop)
            # 内部コマンド: プロセス停止
            shift
            if [[ -d "$PID_DIR" ]]; then
                echo -e "${YELLOW}■ 起動中プロセスを停止しています...${NC}"
                for pidfile in "$PID_DIR"/*.pid; do
                    [[ -f "$pidfile" ]] || continue
                    pid=$(cat "$pidfile")
                    name=$(basename "$pidfile" .pid)
                    if kill -0 "$pid" 2>/dev/null; then
                        kill "$pid" 2>/dev/null || true
                        echo -e "  ${RED}✗${NC} $name (PID $pid) を停止しました"
                    fi
                    rm -f "$pidfile"
                done
                rmdir "$PID_DIR" 2>/dev/null || true
            else
                echo -e "${YELLOW}起動中のプロセスはありません${NC}"
            fi
            exit 0
            ;;
        -h|--help)
            head -24 "$0" | tail -19
            exit 0
            ;;
        *)
            echo -e "${RED}不明なオプション: $1${NC}" >&2
            exit 1
            ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────────
#  ユーティリティ関数
# ──────────────────────────────────────────────────────────────────────────────
log_step()    { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; \
                echo -e "${BLUE}  $1${NC}"; \
                echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
log_ok()      { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn()    { echo -e "  ${YELLOW}!${NC} $1"; }
log_err()     { echo -e "  ${RED}✗${NC} $1"; }
log_info()    { echo -e "  ${CYAN}→${NC} $1"; }

save_pid() {
    # $1 = 名前, $2 = PID
    mkdir -p "$PID_DIR"
    echo "$2" > "$PID_DIR/$1.pid"
}

wait_for_port() {
    # $1 = ポート, $2 = タイムアウト秒, $3 = サービス名
    local port=$1 timeout=${2:-15} name=${3:-service} elapsed=0
    while ! ss -tlnp 2>/dev/null | grep -q ":${port} " && \
          ! netstat -tlnp 2>/dev/null | grep -q ":${port} "; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $timeout ]]; then
            log_warn "$name がポート $port で起動するのを待機中にタイムアウトしました"
            return 1
        fi
    done
    return 0
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        log_err "$1 が見つかりません。インストールしてください。"
        return 1
    fi
}

cleanup() {
    echo ""
    log_step "シャットダウン"
    if [[ -d "$PID_DIR" ]]; then
        for pidfile in "$PID_DIR"/*.pid; do
            [[ -f "$pidfile" ]] || continue
            pid=$(cat "$pidfile")
            name=$(basename "$pidfile" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                wait "$pid" 2>/dev/null || true
                log_ok "$name (PID $pid) を停止しました"
            fi
            rm -f "$pidfile"
        done
        rmdir "$PID_DIR" 2>/dev/null || true
    fi
    echo -e "\n${GREEN}全プロセスを停止しました。${NC}"
}

# Ctrl+C でクリーンアップ
trap cleanup EXIT INT TERM

# ──────────────────────────────────────────────────────────────────────────────
#  自動クリーンアップ: 既存プロセスを無条件に停止してから起動する
#  理由: ./start.sh を --restart なしで再実行すると旧プロセスが残り、
#        WebSocket ポート (8765) が既に使用中になって新プロセスが起動失敗する。
# ──────────────────────────────────────────────────────────────────────────────
if [[ -d "$PID_DIR" ]]; then
    _had_procs=false
    for pidfile in "$PID_DIR"/*.pid; do
        [[ -f "$pidfile" ]] || continue
        pid=$(cat "$pidfile")
        name=$(basename "$pidfile" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            echo -e "  ${YELLOW}!${NC} 旧プロセス $name (PID $pid) を停止しました"
            _had_procs=true
        fi
        rm -f "$pidfile"
    done
    rmdir "$PID_DIR" 2>/dev/null || true
    $_had_procs && echo -e "  ${GREEN}✓${NC} 旧プロセスのクリーンアップ完了"
fi
#  ステップ 0: 前提条件チェック
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 0: 前提条件チェック"

MISSING=false
for cmd in python3 pip3 node npm; do
    if check_command "$cmd"; then
        log_ok "$cmd $(command -v "$cmd")"
    else
        MISSING=true
    fi
done

if $MISSING; then
    log_err "必要なコマンドが不足しています。インストール後に再実行してください。"
    exit 1
fi

log_ok "Python $(python3 --version 2>&1 | awk '{print $2}')"
log_ok "Node   $(node --version)"
log_ok "npm    $(npm --version)"

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 1: Python SDK インストール (cepf_sdk)
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 1: Python SDK インストール (cepf_sdk)"

if python3 -c "import cepf_sdk" 2>/dev/null; then
    log_ok "cepf_sdk は既にインストール済みです"
else
    log_info "pip install -e '.[all]' を実行中..."
    pip3 install -e ".[all]" --quiet 2>&1 | tail -3
    log_ok "cepf_sdk をインストールしました"
fi

# dpkt (PCAP パース用) もインストール
if ! python3 -c "import dpkt" 2>/dev/null; then
    log_info "dpkt をインストール中..."
    pip3 install dpkt --quiet
    log_ok "dpkt をインストールしました"
else
    log_ok "dpkt は既にインストール済みです"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 2: TypeScript ライブラリ ビルド (ws-client → voxel → detector)
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 2: TypeScript ライブラリ ビルド"

TS_PACKAGES=("ws-client" "voxel" "detector")

for pkg in "${TS_PACKAGES[@]}"; do
    log_info "$pkg: npm install..."
    (cd "$pkg" && npm install --silent 2>&1 | tail -1)
    log_info "$pkg: npm run build..."
    (cd "$pkg" && npm run build --silent 2>&1 | tail -1)
    log_ok "$pkg ビルド完了"
done

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 2b: spatial-grid ビルド
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 2b: spatial-grid ビルド"
log_info "spatial-grid: npm install..."
(cd spatial-grid && npm install --silent 2>&1 | tail -1)
log_info "spatial-grid: npm run build..."
(cd spatial-grid && npm run build --silent 2>&1 | tail -1)
log_ok "spatial-grid ビルド完了"

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 3: Viewer バンドル (webpack)
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_VIEWER; then
    log_step "ステップ 3: Viewer バンドル"

    log_info "viewer: npm install..."
    (cd viewer && npm install --silent 2>&1 | tail -1)

    log_info "viewer: webpack バンドル中..."
    (cd viewer && npm run bundle --silent 2>&1 | tail -3)
    log_ok "viewer バンドル完了 → viewer/dist/bundle.js"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 3b: Geo-Viewer バンドル (webpack + CesiumJS)
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_GEO_VIEWER; then
    log_step "ステップ 3b: Geo-Viewer バンドル (CesiumJS)"

    log_info "geo-viewer: npm install..."
    (cd geo-viewer && npm install --silent 2>&1 | tail -1)

    log_info "geo-viewer: webpack バンドル中 (CesiumJS は初回に時間がかかります)..."
    (cd geo-viewer && npm run bundle --silent 2>&1 | tail -3)
    log_ok "geo-viewer バンドル完了 → geo-viewer/dist/bundle.js"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 4: apps_ts 依存インストール
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_DETECTOR; then
    log_step "ステップ 4: apps_ts 依存インストール"

    log_info "apps_ts: npm install..."
    (cd apps_ts && npm install --silent 2>&1 | tail -1)
    log_ok "apps_ts 依存インストール完了"
fi

# install-only モードならここで終了
if $INSTALL_ONLY; then
    log_step "インストール完了"
    log_ok "全依存関係のインストールが完了しました。"
    log_info "起動するには: ./start.sh"
    trap - EXIT INT TERM  # cleanup を解除
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 4c: WebSocket 共通設定
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 4c: WebSocket 共通設定"

# WebSocket ポート設定（環境変数でオーバーライド可能）
if [ -n "${SASS_WS_PORT:-}" ]; then
    WS_PORT="$SASS_WS_PORT"
fi

# 旧バージョンの start.sh が生成した viewer/websocket.json を削除
# （ws://127.0.0.1:8765 固定になるため）
rm -f viewer/websocket.json geo-viewer/websocket.json

# ※ WebSocket URL はブラウザ側で自動解決（resolveWsUrl）
# 優先順位: URL クエリ ?ws= →<meta name="ws-url"> → hostname:8765
# 複数のホスト（localhost, 127.0.0.1, IP アドレスなど）からのアクセスに対応
log_ok "WebSocket: ポート $WS_PORT（ホスト自動解決）"

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 5: パイプライン起動 (ソース → フィルター → WebSocket)
# ──────────────────────────────────────────────────────────────────────────────
log_step "ステップ 5: パイプライン起動 (WebSocket :$WS_PORT)"

mkdir -p "$LOG_DIR"

# パイプラインフィルター設定 (環境変数で追加可能)
PIPELINE_FILTERS="${SASS_PIPELINE_FILTERS:---test-frustum}"

if [[ "$SOURCE_MODE" == "airy" ]]; then
    # ── Airy LiDAR 実機接続モード ──
    if [[ ! -f "$AIRY_CONFIG" ]]; then
        log_err "設定ファイルが見つかりません: $AIRY_CONFIG"
        log_warn "config/sass.json の sensors セクションを確認してください"
        exit 1
    fi
    log_info "ソース: Airy LiDAR 実機 (UDP :$AIRY_PORT, config=$AIRY_CONFIG)"
    log_info "フィルター: $PIPELINE_FILTERS"
    (
        PYTHONPATH="$SCRIPT_DIR" python3 apps/run_pipeline.py \
            --use-airy-live \
            --config "$AIRY_CONFIG" \
            --airy-port "$AIRY_PORT" \
            --ws-port "$WS_PORT" \
            $PIPELINE_FILTERS \
            --verbose
        EXIT_CODE=$?
        echo "$(date '+%Y-%m-%d %H:%M:%S') [WATCHDOG] pipeline exited with code $EXIT_CODE" >> "$LOG_DIR/airy_live.log"
        echo "$(date '+%Y-%m-%d %H:%M:%S') [WATCHDOG] dmesg (last 10 lines):" >> "$LOG_DIR/airy_live.log"
        dmesg | tail -10 >> "$LOG_DIR/airy_live.log" 2>/dev/null || true
    ) > "$LOG_DIR/airy_live.log" 2>&1 &
    REPLAY_PID=$!
    save_pid "airy_live" "$REPLAY_PID"
    log_ok "パイプライン起動 (PID $REPLAY_PID, Airy 実機 + フィルター)"

elif [[ -f "$PCAP_FILE" && -f "$PCAP_META" ]]; then
    # ── PCAP リプレイモード（デフォルト）──
    log_info "ソース: PCAP リプレイ ($PCAP_FILE)"
    log_info "フィルター: $PIPELINE_FILTERS"
    (
        PYTHONPATH="$SCRIPT_DIR" python3 apps/run_pipeline.py \
            --use-pcap \
            --pcap "$PCAP_FILE" \
            --meta "$PCAP_META" \
            --rate "$PCAP_RATE" \
            --loop \
            --ws-port "$WS_PORT" \
            $PIPELINE_FILTERS \
            --verbose
        EXIT_CODE=$?
        echo "$(date '+%Y-%m-%d %H:%M:%S') [WATCHDOG] pipeline exited with code $EXIT_CODE" >> "$LOG_DIR/pcap_replay.log"
        echo "$(date '+%Y-%m-%d %H:%M:%S') [WATCHDOG] dmesg (last 10 lines):" >> "$LOG_DIR/pcap_replay.log"
        dmesg | tail -10 >> "$LOG_DIR/pcap_replay.log" 2>/dev/null || true
    ) > "$LOG_DIR/pcap_replay.log" 2>&1 &
    REPLAY_PID=$!
    save_pid "pcap_replay" "$REPLAY_PID"
    log_ok "パイプライン起動 (PID $REPLAY_PID, PCAP + フィルター)"
elif [[ -f "demo.pcap" ]]; then
    log_info "ソース: 汎用 PCAP リプレイ (demo.pcap, フィルターなし)"
    PYTHONPATH="$SCRIPT_DIR" python3 apps/pcap_replay.py \
        --pcap demo.pcap \
        --parser ouster \
        --loop \
        > "$LOG_DIR/pcap_replay.log" 2>&1 &
    REPLAY_PID=$!
    save_pid "pcap_replay" "$REPLAY_PID"
    log_ok "汎用 PCAP リプレイ起動 (PID $REPLAY_PID, フォールバック)"
else
    log_err "PCAP ファイルが見つかりません: $PCAP_FILE"
    log_warn "SASS_PCAP 環境変数で PCAP ファイルを指定してください"
    log_warn "例: SASS_PCAP=path/to/file.pcap ./start.sh"
    exit 1
fi

# WebSocket サーバーの起動完了を待機
log_info "WebSocket サーバー (ポート $WS_PORT) の起動を待機中..."
if wait_for_port "$WS_PORT" 15 "WebSocket サーバー"; then
    log_ok "WebSocket サーバーがポート $WS_PORT で起動しました"
else
    log_warn "ポートの待機がタイムアウトしました (ログを確認: $LOG_DIR/pcap_replay.log)"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 6: Viewer (HTTP サーバー) 起動
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_VIEWER; then
    log_step "ステップ 6: Viewer 起動 (HTTP :$HTTP_PORT)"

    # voxel_mode を決定
    VIEWER_VOXEL_MODE="${SASS_VOXEL_MODE:-local}"
    $VIEWER_SPLIT && VIEWER_VOXEL_MODE="both"

    # viewer/config.json が存在する場合は保護、ない場合だけ生成
    if [ ! -f "viewer/config.json" ]; then
        log_info "viewer/config.json を初期化中..."
        python3 -c "
import json, pathlib, sys
sass_path = pathlib.Path('config/sass.json')
if not sass_path.exists():
    print('Warning: config/sass.json not found, using defaults', file=sys.stderr)
    obj = {}
else:
    try:
        obj = json.loads(sass_path.read_text())
    except json.JSONDecodeError as e:
        print(f'Warning: config/sass.json parse error: {e}, using defaults', file=sys.stderr)
        obj = {}
inst = obj.get('installation', {})
config = {
    'voxel_mode': '$VIEWER_VOXEL_MODE',
    'voxel_cell_size': obj.get('voxel_cell_size', 1.0),
    'global_voxel_unit_m': 10.0,
    'global_grid_mode': 'wgs84',
    'coin': {},
    'mount': {
        'position': {
            'lat': inst.get('reference_latitude', 0.0),
            'lng': inst.get('reference_longitude', 0.0),
            'alt': inst.get('reference_altitude', 0.0)
        },
        'orientation': inst.get('orientation', {'heading': 0.0, 'pitch': 0.0, 'roll': 0.0}),
        'mounting_type': inst.get('mounting_type', 'pole_mounted')
    }
}
print(json.dumps(config, indent=2, ensure_ascii=False))
" > viewer/config.json
        log_ok "viewer/config.json を生成しました"
    else
        log_ok "viewer/config.json は既に存在します（保護されます）"
    fi

    (cd viewer && npx http-server . -p "$HTTP_PORT" --cors -s --no-cache \
        > "$LOG_DIR/viewer.log" 2>&1) &
    VIEWER_PID=$!
    save_pid "viewer" "$VIEWER_PID"

    if wait_for_port "$HTTP_PORT" 10 "Viewer HTTP サーバー"; then
        log_ok "Viewer 起動完了 (PID $VIEWER_PID)"
        log_info "ブラウザで開く: ${GREEN}http://localhost:$HTTP_PORT${NC}"
    else
        log_warn "Viewer のポート確認がタイムアウトしました (ログ: $LOG_DIR/viewer.log)"
    fi
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 6b: Geo-Viewer 設定生成 + 起動 (HTTP :$GEO_HTTP_PORT)
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_GEO_VIEWER; then
    log_step "ステップ 6b: Geo-Viewer 起動 (CesiumJS HTTP :$GEO_HTTP_PORT)"

    # geo-viewer/config.json が存在する場合は保護、ない場合だけ生成
    if [ ! -f "geo-viewer/config.json" ]; then
        log_info "geo-viewer/config.json を初期化中..."
        python3 -c "
import json, pathlib, sys
sass_path = pathlib.Path('config/sass.json')
if not sass_path.exists():
    print('Warning: config/sass.json not found, using defaults', file=sys.stderr)
    obj = {}
else:
    try:
        obj = json.loads(sass_path.read_text())
    except json.JSONDecodeError as e:
        print(f'Warning: config/sass.json parse error: {e}, using defaults', file=sys.stderr)
        obj = {}
inst = obj.get('installation', {})
config = {
    'mount': {
        'position': {
            'lat': inst.get('reference_latitude', 0.0),
            'lng': inst.get('reference_longitude', 0.0),
            'alt': inst.get('reference_altitude', 0.0)
        },
        'orientation': inst.get('orientation', {'heading': 0.0, 'pitch': 0.0, 'roll': 0.0}),
        'mounting_type': inst.get('mounting_type', 'pole_mounted')
    }
}
print(json.dumps(config, indent=2, ensure_ascii=False))
" > geo-viewer/config.json
        log_ok "geo-viewer/config.json を生成しました"
    else
        log_ok "geo-viewer/config.json は既に存在します（保護されます）"
    fi

    (cd geo-viewer && npx http-server . -p "$GEO_HTTP_PORT" --cors -s \
        > "$LOG_DIR/geo_viewer.log" 2>&1) &
    GEO_VIEWER_PID=$!
    save_pid "geo_viewer" "$GEO_VIEWER_PID"

    if wait_for_port "$GEO_HTTP_PORT" 10 "Geo-Viewer HTTP サーバー"; then
        log_ok "Geo-Viewer 起動完了 (PID $GEO_VIEWER_PID)"
        log_info "ブラウザで開く: ${GREEN}http://localhost:$GEO_HTTP_PORT${NC}"
    else
        log_warn "Geo-Viewer のポート確認がタイムアウトしました (ログ: $LOG_DIR/geo_viewer.log)"
    fi
fi

# ──────────────────────────────────────────────────────────────────────────────
#  ステップ 7: Detector (ヘッドレス侵入検知) 起動
# ──────────────────────────────────────────────────────────────────────────────
if $RUN_DETECTOR; then
    log_step "ステップ 7: Detector 起動 (ヘッドレス侵入検知)"

    (cd apps_ts && node --loader ts-node/esm src/main-detector.ts \
        > "$LOG_DIR/detector.log" 2>&1) &
    DETECTOR_PID=$!
    save_pid "detector" "$DETECTOR_PID"
    log_ok "Detector 起動 (PID $DETECTOR_PID)"
    log_info "ログ: $LOG_DIR/detector.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  起動完了サマリー
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  SASS 起動完了!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${CYAN}WebSocket${NC}   ws://0.0.0.0:$WS_PORT"
$RUN_VIEWER     && echo -e "  ${CYAN}Viewer${NC}      http://localhost:$HTTP_PORT   (Three.js)"
$RUN_GEO_VIEWER && echo -e "  ${CYAN}Geo-Viewer${NC}  http://localhost:$GEO_HTTP_PORT  (CesiumJS)"
$RUN_DETECTOR   && echo -e "  ${CYAN}Detector${NC}    ヘッドレスモード (ログ: .logs/detector.log)"
echo ""
echo -e "  ログディレクトリ: ${YELLOW}$LOG_DIR/${NC}"
echo -e "  停止するには:     ${YELLOW}Ctrl+C${NC} または ${YELLOW}./start.sh --stop${NC}"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
#  フォアグラウンド待機 (Ctrl+C で cleanup が呼ばれる)
# ──────────────────────────────────────────────────────────────────────────────
echo "$(date '+%Y-%m-%d %H:%M:%S') [start.sh] フォアグラウンド待機開始 (PIDs in $PID_DIR/)" >> "$LOG_DIR/startup.log"

# set -e の影響で wait の非ゼロ終了がスクリプト終了を引き起こす場合がある。
# 無限ループ化して、子プロセスが終了しても再チェックする。
while true; do
    # 少なくとも pcap_replay が生きているか確認
    if [[ -f "$PID_DIR/pcap_replay.pid" ]]; then
        REPLAY_PID=$(cat "$PID_DIR/pcap_replay.pid")
        if ! kill -0 "$REPLAY_PID" 2>/dev/null; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') [start.sh] pcap_replay (PID $REPLAY_PID) が終了しました" >> "$LOG_DIR/startup.log"
            log_err "pcap_replay プロセスが終了しました。ログを確認: $LOG_DIR/pcap_replay.log"
            break
        fi
    fi
    sleep 5
done
