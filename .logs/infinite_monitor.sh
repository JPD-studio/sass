#!/bin/bash
# 無限監視スクリプト — Ctrl+C で停止するまで継続
MONITOR_LOG=".logs/infinite_monitor_$(date +%Y%m%d_%H%M%S).log"
echo "=== 無限監視開始 ===" | tee "$MONITOR_LOG"
echo "Ctrl+C で停止してください" | tee -a "$MONITOR_LOG"
echo "監視ログ: $MONITOR_LOG" | tee -a "$MONITOR_LOG"
echo "" | tee -a "$MONITOR_LOG"

ITERATION=0
ALERT_COUNT=0

trap "echo ''; echo '[停止] 無限監視を終了します'; echo '最終統計:'; echo '  観測回数: '$ITERATION; echo '  アラート: '$ALERT_COUNT; exit 0" INT TERM

while true; do
    ITERATION=$((ITERATION + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # === 基本プロセス確認 ===
    PCAP_PID=$(pgrep -f "ouster_pcap_replay" || echo "DEAD")
    VIEWER_PID=$(pgrep -f "http-server.*3000" | head -1 || echo "DEAD")
    
    # === ポート確認 ===
    WS_LISTEN=$(ss -tlnp 2>/dev/null | grep -c ":8765 ")
    
    # === PCAP メモリ + CPU ===
    if [[ "$PCAP_PID" != "DEAD" ]]; then
        RSS_KB=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep -i vmrss | awk '{print $2}' || echo "0")
        RSS_MB=$((RSS_KB / 1024))
        CPU=$(ps aux 2>/dev/null | grep "^[^ ]* *$PCAP_PID " | awk '{print $3}' | head -1 || echo "0")
        THREADS=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep Threads | awk '{print $2}' || echo "?")
        FDs=$(ls /proc/$PCAP_PID/fd 2>/dev/null | wc -l)
        ALIVE_STATUS="✓"
    else
        RSS_MB="0"
        CPU="0"
        THREADS="?"
        FDs="0"
        ALIVE_STATUS="✗"
        ALERT_COUNT=$((ALERT_COUNT + 1))
    fi
    
    # === ログから実際のエラー数を取得 ===
    # 最後のパス完了ログから send_errors の値を取得（最も信頼性が高い）
    ACTUAL_ERRORS=$(grep "send_errors=" .logs/pcap_replay.log 2>/dev/null | tail -1 | grep -o "send_errors=[0-9]*" | cut -d= -f2 || echo "0")
    FRAMES_SENT=$(grep "total_sent=" .logs/pcap_replay.log 2>/dev/null | tail -1 | grep -o "total_sent=[0-9]*" | cut -d= -f2 || echo "0")
    
    # === パス/フレーム統計 ===
    PASS_COUNT=$(grep -c "パス.*完了" .logs/pcap_replay.log 2>/dev/null || echo "0")
    
    # === 接続数確認（WebSocket クライアント） ===
    CLIENT_COUNT=$(grep -c "client connected" .logs/pcap_replay.log 2>/dev/null | head -1 || echo "0")
    
    # === ステータス行出力 ===
    STATUS_LINE="[$TIMESTAMP|#$ITERATION] PCAP=$ALIVE_STATUS($PCAP_PID|${RSS_MB}MB|CPU${CPU}%|${THREADS}th|FDs=$FDs) | WS_LISTEN=$WS_LISTEN | Errors=$ACTUAL_ERRORS | Frames=$FRAMES_SENT | Passes=$PASS_COUNT | Clients=$CLIENT_COUNT"
    
    echo "$STATUS_LINE" | tee -a "$MONITOR_LOG"
    
    # === 異常検出 ===
    ANOMALY=0
    
    if [[ "$PCAP_PID" == "DEAD" && $ITERATION -gt 2 ]]; then
        echo "[🔴 CRITICAL] PCAPプロセスが停止しました! $(date)" | tee -a "$MONITOR_LOG"
        ALERT_COUNT=$((ALERT_COUNT + 1))
        ANOMALY=1
    fi
    
    if [[ $WS_LISTEN -eq 0 && $ITERATION -gt 2 ]]; then
        echo "[🟠 WARNING] WebSocketポートがリッスンしていません" | tee -a "$MONITOR_LOG"
        ALERT_COUNT=$((ALERT_COUNT + 1))
        ANOMALY=1
    fi
    
    if [[ $RSS_MB -gt 500 ]]; then
        echo "[🟡 INFO] メモリ使用量が高い: ${RSS_MB}MB" | tee -a "$MONITOR_LOG"
    fi
    
    if [[ "$ACTUAL_ERRORS" != "?" && "$ACTUAL_ERRORS" != "0" && ! -z "$ACTUAL_ERRORS" ]]; then
        echo "[🟡 INFO] WebSocket送信エラー検出: $ACTUAL_ERRORS" | tee -a "$MONITOR_LOG"
    fi
    
    # === 3回連続異常で停止 ===
    if [[ $ANOMALY -eq 1 ]]; then
        if [[ $ALERT_COUNT -ge 3 ]]; then
            echo "" | tee -a "$MONITOR_LOG"
            echo "[🔴 STOP] 異常が連続で検出されたため監視を終了します" | tee -a "$MONITOR_LOG"
            break
        fi
    fi
    
    sleep 30
done

echo "" | tee -a "$MONITOR_LOG"
echo "=== 監視ログ終了 ===" | tee -a "$MONITOR_LOG"
echo "最終ログファイル: $MONITOR_LOG"

