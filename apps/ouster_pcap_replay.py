#!/usr/bin/env python3
# apps/ouster_pcap_replay.py
"""
Ouster OS-1 PCAP (pcapng / IP フラグメント対応) を読み込み、
点群フレームを WebSocket でブロードキャストするリプレイツール。

ouster-sdk (>=0.16) を使用して正確にパケットをデコードします。
IP フラグメントを再結合して LidarPacket → ScanBatcher → XYZLut で XYZ 変換。

使い方:
    PYTHONPATH=/home/jetson/repos/sass python3 apps/ouster_pcap_replay.py \\
        --pcap  pcap/250808sbir_20250808133236_00001.pcap \\
        --meta  pcap/os1-128-rng19.json \\
        --rate  1.0 --loop

依存: pip install dpkt websockets numpy ouster-sdk
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import resource
import struct
import sys
import time
import traceback
import warnings
from pathlib import Path
from typing import Dict, Iterator, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _log_resource_usage(label: str = "") -> None:
    """RSS メモリ使用量と FD 数をログに出力するユーティリティ。"""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = ru.ru_maxrss / 1024  # Linux: KB → MB
        pid = os.getpid()
        fd_count = len(os.listdir(f"/proc/{pid}/fd"))
        logger.info("[RESOURCE %s] PID=%d RSS=%.1f MB, FDs=%d", label, pid, rss_mb, fd_count)
    except Exception as e:
        logger.debug("[RESOURCE] 取得失敗: %s", e)


# ------------------------------------------------------------------ #
# IP フラグメント再結合 → UDP ペイロードイテレーター                     #
# ------------------------------------------------------------------ #

def _iter_udp_payloads(pcap_path: Path,
                       lidar_port: int = 7502) -> Iterator[Tuple[float, bytes]]:
    """
    pcapng/pcap を読み込み、IP フラグメントを再結合して
    指定 UDP ポート宛の UDP ペイロード (ヘッダー除く) を yield する。
    """
    try:
        import dpkt
        import dpkt.pcapng
    except ImportError:
        logger.error("dpkt が必要: python3 -m pip install dpkt"); sys.exit(1)

    magic = pcap_path.read_bytes()[:4]
    fh    = open(pcap_path, "rb")
    reader = dpkt.pcapng.Reader(fh) if magic == b"\x0a\x0d\x0d\x0a" else dpkt.pcap.Reader(fh)

    # key: (src_ip, dst_ip, ip_id) → list of (offset, data_bytes, is_first, udp_header_8b)
    frags: Dict[tuple, list] = {}
    frag_ts: Dict[tuple, float] = {}

    try:
        for ts, buf in reader:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                if not isinstance(eth.data, dpkt.ip.IP):
                    continue
                ip = eth.data
                if ip.p != 17:        # UDP のみ
                    continue

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    off_raw = ip.off

                mf       = bool((off_raw >> 13) & 0x1)
                frag_off = (off_raw & 0x1FFF) * 8
                key      = (bytes(ip.src), bytes(ip.dst), ip.id)

                if isinstance(ip.data, dpkt.udp.UDP):
                    # 最初のフラグメント: UDP ヘッダー + ペイロード
                    udp_hdr = bytes(ip.data)[:8]
                    frags.setdefault(key, []).append(
                        (frag_off, bytes(ip.data.data), True, udp_hdr))
                    frag_ts.setdefault(key, float(ts))
                else:
                    # 後続フラグメント: IP ペイロードが UDP ペイロードの続き
                    frags.setdefault(key, []).append(
                        (frag_off, bytes(ip.data), False, None))

                if not mf:
                    # 最終フラグメント到達 → 再結合
                    parts   = frags.pop(key, [])
                    emit_ts = frag_ts.pop(key, float(ts))
                    parts.sort(key=lambda x: x[0])

                    # UDP 宛先ポートを確認 (最初のフラグメントの UDP ヘッダーから)
                    udp_hdr = next((h for _, _, u, h in parts if u and h), None)
                    if udp_hdr is None:
                        continue
                    _sport, dport = struct.unpack("!HH", udp_hdr[:4])
                    if dport != lidar_port:
                        continue

                    payload = b"".join(data for _, data, _, _ in parts)
                    if payload:
                        yield emit_ts, payload
            except Exception:
                pass
    finally:
        fh.close()


# ------------------------------------------------------------------ #
# ouster-sdk を使ったフレームイテレーター                               #
# ------------------------------------------------------------------ #

def iter_frames(pcap_path: Path, meta_path: Path) -> Iterator[Tuple[float, np.ndarray]]:
    """
    PCAP から IP フラグメントを再結合し、ouster-sdk で XYZ 点群を生成して yield する。
    """
    try:
        from ouster.sdk.core import SensorInfo, XYZLut, ChanField
        from ouster.sdk._bindings.client import PacketFormat as PF, LidarPacket, ScanBatcher, LidarScan
    except ImportError:
        logger.error("ouster-sdk が必要: pip install ouster-sdk"); sys.exit(1)

    with open(meta_path) as f:
        info = SensorInfo(f.read())
    pf      = PF(info)
    xyz_lut = XYZLut(info)
    pkt_sz  = pf.lidar_packet_size

    logger.info("センサー設定: lidar_packet_size=%d, udp_profile=%s",
                pkt_sz, info.format.udp_profile_lidar)

    batcher = ScanBatcher(info)
    scan    = LidarScan(info)

    frame_ts = 0.0
    for ts, payload in _iter_udp_payloads(pcap_path):
        if len(payload) != pkt_sz:
            logger.debug("パケットサイズ不一致: %d (expected %d)", len(payload), pkt_sz)
            continue

        pkt = LidarPacket(pkt_sz)
        pkt.buf[:] = np.frombuffer(payload, dtype=np.uint8)

        if frame_ts == 0.0:
            frame_ts = ts

        if batcher(pkt, scan):
            # フレーム完成 → XYZ 変換
            xyz   = xyz_lut(scan).reshape(-1, 3).astype(np.float32)
            rng   = scan.field(ChanField.RANGE).reshape(-1)
            valid = rng > 0
            pts   = xyz[valid]

            yield frame_ts, pts
            frame_ts = ts   # 次フレームのタイムスタンプ初期化


# ------------------------------------------------------------------ #
# WebSocket 配信                                                        #
# ------------------------------------------------------------------ #

async def replay(pcap_path: Path, meta_path: Path,
                 host: str, port: int, rate: float, loop_forever: bool) -> None:
    from cepf_sdk.transport.websocket_server import WebSocketTransport

    logger.info("[DIAG] replay() 開始: PID=%d", os.getpid())
    _log_resource_usage("STARTUP")

    transport = WebSocketTransport(host=host, port=port)
    await transport.start()
    logger.info("WebSocket サーバー起動: ws://%s:%d", host, port)
    logger.info("ブラウザ: http://192.168.10.15:3000 または http://localhost:3000")

    if transport.client_count == 0:
        logger.info("ブラウザ接続待機中... (http://192.168.10.15:3000 を開いてください)")
        while transport.client_count == 0:
            await asyncio.sleep(0.5)
        logger.info("クライアント接続。PCAP 読み込みを開始します...")

    pass_num = 0
    total_send_errors = 0
    total_frames_sent = 0
    while True:
        pass_num += 1
        logger.info("パス %d: ストリーミング開始 (%s)", pass_num, pcap_path.name)

        frame_id   = 0
        first_ts   = None
        start_mono = time.monotonic()
        pass_send_errors = 0

        try:
            for ts, pts in iter_frames(pcap_path, meta_path):
                if first_ts is None:
                    first_ts = ts

                if rate > 0 and frame_id > 0:
                    elapsed_pcap = ts - first_ts
                    elapsed_real = (time.monotonic() - start_mono) * rate
                    wait = elapsed_pcap / rate - (time.monotonic() - start_mono)
                    if wait > 0:
                        await asyncio.sleep(wait)

                if pts is not None and len(pts) > 0:
                    payload_str = json.dumps({
                        "frame_id": frame_id,
                        "timestamp": float(ts),
                        "points": {
                            "x": pts[:, 0].tolist(),
                            "y": pts[:, 1].tolist(),
                            "z": pts[:, 2].tolist(),
                        },
                    })

                    payload_kb = len(payload_str) / 1024

                    if transport.client_count > 0:
                        from websockets.exceptions import ConnectionClosed
                        dead = set()
                        for ws in list(transport._clients):
                            try:
                                await ws.send(payload_str)
                            except ConnectionClosed as e:
                                dead.add(ws)
                                pass_send_errors += 1
                                total_send_errors += 1
                                logger.warning("[DIAG] WebSocket send ConnectionClosed: %s (total_errors=%d)", e, total_send_errors)
                            except Exception as e:
                                dead.add(ws)
                                pass_send_errors += 1
                                total_send_errors += 1
                                logger.error("[DIAG] WebSocket send unexpected error: %s\n%s", e, traceback.format_exc())
                        transport._clients -= dead
                        if dead:
                            logger.info("[DIAG] 切断クライアント除去: %d 件, 残り %d 件", len(dead), transport.client_count)

                    if frame_id % 20 == 0:
                        logger.info("  フレーム %d  (%d 点, %.1f KB, clients=%d)",
                                    frame_id, len(pts), payload_kb, transport.client_count)

                    # 100フレームごとにリソースを記録
                    if frame_id % 100 == 0:
                        _log_resource_usage(f"PASS{pass_num}_F{frame_id}")

                frame_id += 1
                total_frames_sent += 1
                # 他の非同期タスクに制御を渡す
                if frame_id % 4 == 0:
                    await asyncio.sleep(0)

        except Exception as e:
            logger.error("[DIAG] パス %d フレーム処理中に例外: %s\n%s", pass_num, e, traceback.format_exc())

        elapsed_pass = time.monotonic() - start_mono
        logger.info("パス %d 完了 (%d フレーム, %.1f 秒, send_errors=%d, total_sent=%d)",
                    pass_num, frame_id, elapsed_pass, pass_send_errors, total_frames_sent)
        _log_resource_usage(f"PASS{pass_num}_END")

        if not loop_forever:
            break
        logger.info("ループ再生: 2 秒後に再スタート...")
        await asyncio.sleep(2.0)

    logger.info("[DIAG] replay() 終了: total_passes=%d, total_frames=%d, total_send_errors=%d",
                pass_num, total_frames_sent, total_send_errors)
    await transport.stop()


# ------------------------------------------------------------------ #
# エントリーポイント                                                    #
# ------------------------------------------------------------------ #

def main() -> None:
    p = argparse.ArgumentParser(
        description="Ouster IP フラグメント PCAP → Three.js ビューワー"
    )
    p.add_argument("--pcap", "-f", required=True)
    p.add_argument("--meta", "-m", default="pcap/os1-128-rng19.json")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--rate", type=float, default=1.0, help="再生速度倍率 (0=最速)")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pcap_path = Path(args.pcap)
    meta_path = Path(args.meta)
    if not pcap_path.exists():
        logger.error("PCAP が見つかりません: %s", pcap_path); sys.exit(1)
    if not meta_path.exists():
        logger.error("メタ JSON が見つかりません: %s", meta_path); sys.exit(1)

    try:
        asyncio.run(replay(pcap_path, meta_path, args.host, args.port, args.rate, args.loop))
    except KeyboardInterrupt:
        logger.info("[DIAG] KeyboardInterrupt で停止")
    except Exception as e:
        logger.error("[DIAG] 予期せぬトップレベル例外: %s\n%s", e, traceback.format_exc())
        sys.exit(1)
    finally:
        logger.info("[DIAG] main() 終了 (PID=%d)", os.getpid())


if __name__ == "__main__":
    main()
