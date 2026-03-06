#!/usr/bin/env python3
# apps/pcap_replay.py
"""
PCAP ファイルを読み込み、点群フレームを WebSocket でブロードキャストするリプレイツール。

使い方:
    python apps/pcap_replay.py --pcap data/sample.pcap --parser velodyne
    python apps/pcap_replay.py --pcap data/sample.pcap --parser ouster --rate 2.0
    python apps/pcap_replay.py --pcap data/sample.pcap --parser velodyne --loop

依存パッケージ (未インストールの場合):
    pip install dpkt websockets numpy
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# パーサー選択                                                         #
# ------------------------------------------------------------------ #

PARSER_CHOICES = ["velodyne", "velodyne32", "ouster", "ouster128", "ti_radar"]

def _make_parser(name: str):
    """パーサー名から RawDataParser インスタンスを生成する。"""
    if name in ("velodyne", "velodyne16"):
        from cepf_sdk.parsers.velodyne import VelodyneLidarParser
        from cepf_sdk.config import SensorConfig
        from cepf_sdk.enums import SensorType
        return VelodyneLidarParser(
            SensorConfig(sensor_type=SensorType.LIDAR, model="Velodyne VLP-16", num_channels=16)
        )
    elif name == "velodyne32":
        from cepf_sdk.parsers.velodyne import VelodyneLidarParser
        from cepf_sdk.config import SensorConfig
        from cepf_sdk.enums import SensorType
        return VelodyneLidarParser(
            SensorConfig(sensor_type=SensorType.LIDAR, model="Velodyne VLP-32C", num_channels=32)
        )
    elif name == "ouster":
        from cepf_sdk.parsers.ouster import OusterLidarParser
        return OusterLidarParser()
    elif name == "ouster128":
        from cepf_sdk.parsers.ouster_dome128 import OusterDome128Parser
        return OusterDome128Parser()
    elif name == "ti_radar":
        from cepf_sdk.parsers.ti_radar import TiRadarParser
        return TiRadarParser()
    else:
        raise ValueError(f"未対応のパーサー: {name}")


# ------------------------------------------------------------------ #
# PCAP 読み込み                                                        #
# ------------------------------------------------------------------ #

def _read_udp_payloads(pcap_path: Path) -> Iterator[tuple[float, bytes]]:
    """
    PCAP ファイルから UDP ペイロードを (timestamp, payload) として yield する。
    dpkt が必要 (pip install dpkt)。
    """
    try:
        import dpkt
    except ImportError:
        logger.error("dpkt が必要です: pip install dpkt")
        sys.exit(1)

    with open(pcap_path, "rb") as f:
        try:
            pcap = dpkt.pcap.Reader(f)
        except Exception as e:
            logger.error("PCAP ファイルのオープンに失敗: %s", e)
            sys.exit(1)

        for ts, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
            except Exception:
                continue

            ip = getattr(eth, "data", None)
            if not isinstance(ip, (dpkt.ip.IP, dpkt.ip6.IP6)):
                continue

            udp = getattr(ip, "data", None)
            if not isinstance(udp, dpkt.udp.UDP):
                continue

            yield float(ts), bytes(udp.data)


# ------------------------------------------------------------------ #
# メインリプレイループ                                                  #
# ------------------------------------------------------------------ #

async def replay(
    pcap_path: Path,
    parser_name: str,
    host: str,
    port: int,
    rate: float,
    loop_forever: bool,
    verbose: bool,
) -> None:
    from cepf_sdk.transport.websocket_server import WebSocketTransport
    from cepf_sdk.errors import ParseError

    parser = _make_parser(parser_name)
    transport = WebSocketTransport(host=host, port=port)
    await transport.start()
    logger.info("サーバー起動: ws://%s:%d", host, port)
    logger.info("ブラウザで viewer/index.html を開いてください (例: http://localhost:3000)")

    pass_num = 0
    while True:
        pass_num += 1
        logger.info("パス %d: %s を読み込み中...", pass_num, pcap_path)

        packets = list(_read_udp_payloads(pcap_path))
        if not packets:
            logger.error("UDP パケットが見つかりません: %s", pcap_path)
            break

        logger.info("  %d パケット取得", len(packets))

        first_ts = packets[0][0]
        replay_start = time.monotonic()
        frame_count = 0
        skip_count = 0

        for i, (pkt_ts, payload) in enumerate(packets):
            # クライアントが接続するまで最初のフレームで待機
            if frame_count == 0 and transport.client_count == 0:
                logger.info("  クライアント接続待ち... (ブラウザで index.html を開いてください)")
                while transport.client_count == 0:
                    await asyncio.sleep(0.5)
                logger.info("  クライアント接続。リプレイ開始。")
                replay_start = time.monotonic()
                first_ts = pkt_ts  # タイミングをリセット

            # オリジナルのタイムスタンプに合わせて再生速度を制御
            if rate > 0 and i > 0:
                elapsed_real = (time.monotonic() - replay_start) * rate
                elapsed_pcap = pkt_ts - first_ts
                sleep_time = elapsed_pcap - elapsed_real
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            try:
                frame = parser.parse(payload)
                await transport.send(frame)
                frame_count += 1
                if verbose:
                    logger.debug(
                        "  フレーム #%d: %d 点",
                        frame.metadata.frame_id,
                        frame.metadata.point_count,
                    )
                elif frame_count % 50 == 0:
                    logger.info("  %d フレーム送信済み", frame_count)
            except Exception:
                skip_count += 1

        logger.info(
            "パス %d 完了: %d フレーム送信, %d スキップ",
            pass_num, frame_count, skip_count,
        )

        if not loop_forever:
            break

        logger.info("ループ再生: 2 秒後に再スタート...")
        await asyncio.sleep(2.0)

    await transport.stop()
    logger.info("サーバー停止")


# ------------------------------------------------------------------ #
# エントリーポイント                                                    #
# ------------------------------------------------------------------ #

def main() -> None:
    p = argparse.ArgumentParser(
        description="PCAP ファイルをリプレイして Three.js ビューワーに配信"
    )
    p.add_argument(
        "--pcap", "-f",
        required=True,
        help="PCAP ファイルパス",
    )
    p.add_argument(
        "--parser",
        choices=PARSER_CHOICES,
        default="velodyne",
        help="使用するパーサー (default: velodyne)",
    )
    p.add_argument(
        "--host",
        default="0.0.0.0",
        help="WebSocket ホスト (default: 0.0.0.0)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket ポート (default: 8765)",
    )
    p.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="再生速度倍率 (1.0=実時間, 2.0=2倍速, 0=最速, default: 1.0)",
    )
    p.add_argument(
        "--loop",
        action="store_true",
        help="ファイル末尾に達したら先頭に戻ってループ再生",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログ",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pcap_path = Path(args.pcap)
    if not pcap_path.exists():
        logger.error("PCAP ファイルが見つかりません: %s", pcap_path)
        sys.exit(1)

    asyncio.run(
        replay(
            pcap_path=pcap_path,
            parser_name=args.parser,
            host=args.host,
            port=args.port,
            rate=args.rate,
            loop_forever=args.loop,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
