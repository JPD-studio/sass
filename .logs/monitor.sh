#!/bin/bash
# WebSocketプロセスモニター
LOG_DIR="/home/jetson/repos/sass/.logs"
while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # pcap_replay プロセスの確認
    PCAP_PID=$(pgrep -f "ouster_pcap_replay" || echo "DEAD")
    
    # ポート8765のリスニング確認
    WS_LISTEN=$(ss -tlnp 2>/dev/null | grep ":8765 " | wc -l)
    
    # メモリ使用量 (pcap_replay)
    if [[ "$PCAP_PID" != "DEAD" ]]; then
        RSS_KB=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep -i vmrss | awk '{print $2}')
        RSS_MB=$((RSS_KB / 1024))
        FD_COUNT=$(ls /proc/$PCAP_PID/fd 2>/dev/null | wc -l)
        THREADS=$(cat /proc/$PCAP_PID/status 2>/dev/null | grep Threads | awk '{print $2}')
    else
        RSS_MB="N/A"
        FD_COUNT="N/A"
        THREADS="N/A"
    fi
    
    echo "$TIMESTAMP | PID=$PCAP_PID WS_LISTEN=$WS_LISTEN RSS=${RSS_MB}MB FDs=$FD_COUNT Threads=$THREADS" >> "$LOG_DIR/monitor.log"
    
    if [[ "$PCAP_PID" == "DEAD" ]]; then
        echo "$TIMESTAMP | *** PCAP REPLAY PROCESS DIED ***" >> "$LOG_DIR/monitor.log"
        # dmesg でOOMキラーのログを確認
        dmesg 2>/dev/null | tail -20 >> "$LOG_DIR/monitor.log"
        echo "$TIMESTAMP | Last 20 lines of pcap_replay.log:" >> "$LOG_DIR/monitor.log"
        tail -20 "$LOG_DIR/pcap_replay.log" >> "$LOG_DIR/monitor.log"
        break
    fi
    
    sleep 10
done
