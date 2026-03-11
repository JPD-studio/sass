# apps/run_pipeline.py
"""パイプラインエントリーポイント"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path

from cepf_sdk import UnifiedSenseCloud
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.sources import AiryLiveSource
from cepf_sdk.transport import WebSocketTransport

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="CEPF USC Pipeline")
    parser.add_argument(
        "--config", "-c",
        default="sensors.json",
        help="センサー設定 JSON ファイルパス (default: sensors.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログを出力",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("設定ファイルが見つかりません: %s", config_path)
        logger.info("sensors.example.json をコピーして sensors.json を作成してください。")
        sys.exit(1)

    # JSON から USC を初期化
    usc = UnifiedSenseCloud.from_json(str(config_path))
    logger.info("USC initialized from %s", config_path)

    # フィルターの追加例
    pipeline = FilterPipeline(
        filters=[
            CylindricalFilter(radius_m=50.0, z_min_m=-2.0, z_max_m=30.0),
        ],
        verbose=args.verbose,
    )
    usc.add_filter(lambda frame: _apply_pipeline(frame, pipeline))

    logger.info("Pipeline ready. Waiting for sensor data...")

    transport = None
    ws_loop = None
    # WebSocket 配信を有効にする場合はこの1行を有効に、無効にする場合はコメントアウト
    transport, ws_loop = _start_websocket_server()

    source = AiryLiveSource(usc, sensor_id="lidar", port=6699)
    for frame in source.frames():
        process_frame(frame, transport, ws_loop)


def _start_websocket_server(host: str = "0.0.0.0", port: int = 8765):
    """WebSocket サーバーをバックグラウンドスレッドで起動する。"""
    transport = WebSocketTransport(host=host, port=port)
    loop = asyncio.new_event_loop()

    def _thread() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(transport.start())
        loop.run_forever()

    threading.Thread(target=_thread, daemon=True).start()
    logger.info("WebSocket server started on ws://%s:%d", host, port)
    return transport, loop


def process_frame(frame, transport=None, ws_loop=None) -> None:
    """スキャン 1 フレーム分の処理。"""
    import numpy as np
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is not None and len(x) > 0:
        r = np.sqrt(np.asarray(x)**2 + np.asarray(y)**2 + np.asarray(z)**2)
        p = np.percentile(r, [5, 25, 50, 75, 95])
        logger.info("frame: points=%d  range min=%.3f p5=%.3f p25=%.3f median=%.3f p75=%.3f p95=%.3f max=%.3f [m]",
                    frame.point_count, float(np.min(r)),
                    p[0], p[1], p[2], p[3], p[4], float(np.max(r)))
    if transport is not None and ws_loop is not None:
        asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)


def _apply_pipeline(frame, pipeline: FilterPipeline):
    """FilterPipeline を CepfFrame に適用する"""
    from dataclasses import replace
    result = pipeline.apply(frame.points)
    return replace(frame, points=result.points, point_count=result.count_after)


if __name__ == "__main__":
    main()
