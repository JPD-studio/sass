#!/bin/bash
# 1時間の詳細監視スクリプト
LOG_FILE=".logs/observation_$(date +%Y%m%d_%H%M%S).log"
DURATION=$((3600))  # 1時間（秒）
INTERVAL=30         # 30秒ごとにチェック
ELAPSED=0

echo "=== 1時間の詳細監視開始 ===" | tee "$LOG_FILE"
echo "ログファイル: $LOG_FILE" | tee -a "$LOG_FILE"
echo "監視間隔: ${INTERVAL}秒" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

while [[ $ELAPSED -lt $DURATION ]]; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # 1. プロセス確認
    PCAP_PID=$(pgrep -f "ouster_pcap_replay" || echo "DEAD")
    VIEWER_PID=$(pgrep -f "http-server.*3000" | head -1 || echo "DEAD")
    GEO_VIEWER_PID=$(pgrep -f "http-server.*3001" | head -1 || echo "DEAD")
    DETECTOR_PID=$(pgrep -f "main-detector" || echo "DEAD")
    
    # 2. ポート確認
    WS_PORT=$(ss -tlnp 2>/dev/null | grep -c ":8765 ")
    
    # 3. メモリ確認（pcap_replay）
    if [[ "$PCAP_PID" != "DEAD" ]]; then
        RSS_KB=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep -i vmrss | awk '{print $2}')
        RSS_MB=$((RSS_KB / 1024))
        CPU=$(ps aux | grep $PCAP_PID | grep -v grep | awk '{print $3}')
        THREADS=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep Threads | awk '{print $2}')
        FDs=$(ls /proc/$PCAP_PID/fd 2>/dev/null | wc -l)
    else
        RSS_MB="N/A"
        CPU="N/A"
        THREADS="N/A"
        FDs="N/A"
    fi
    
    # 4. フレーム数確認
    FRAME_COUNT=$(grep -c "フレーム" .logs/pcap_replay.log 2>/dev/null || echo "0")
    PASS_COUNT=$(grep -c "パス.*完了" .logs/pcap_replay.log 2>/dev/null || echo "0")
    
    # 5. エラー確認（send_errors=N を抽出）
    ERROR_COUNT=$(grep -o "send_errors=[0-9]*" .logs/pcap_replay.log 2>/dev/null | tail -1 | awk -F'=' '{print $2}' || echo "0")
    
    # ログ出力
    STATUS_LINE="[$TIMESTAMP] E=${ELAPSED}s | PCAP=$PCAP_PID(${RSS_MB}MB,${CPU}%,${THREADS}th,${FDs}fd) | WS=${WS_PORT} | Viewer=${VIEWER_PID} | Total=${PASS_COUNT}pass,${FRAME_COUNT}frames | Errors=${ERROR_COUNT}"
    
    echo "$STATUS_LINE" | tee -a "$LOG_FILE"
    
    # 異常検出
    if [[ "$PCAP_PID" == "DEAD" && $ELAPSED -gt 60 ]]; then
        echo "[ERROR] *** PCAP RELAY DIED AT $TIMESTAMP (elapsed ${ELAPSED}s) ***" | tee -a "$LOG_FILE"
        dmesg | tail -20 >> "$LOG_FILE"
        break
    fi
    
    if [[ $ERROR_COUNT -gt 0 ]]; then
        echo "[WARN] Errors detected: $ERROR_COUNT" | tee -a "$LOG_FILE"
        tail -5 .logs/pcap_replay.log | grep -i error >> "$LOG_FILE"
    fi
    
    ELAPSED=$((ELAPSED + INTERVAL))
    sleep $INTERVAL
done

echo "" | tee -a "$LOG_FILE"
echo "=== 1時間監視完了 ===" | tee -a "$LOG_FILE"
echo "最終ログ：$LOG_FILE"
