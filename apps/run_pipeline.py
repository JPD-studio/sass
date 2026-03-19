# apps/run_pipeline.py
"""パイプラインエントリーポイント"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path

import numpy as np

from cepf_sdk import UnifiedSenseCloud
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.range.frustum import FrustumFilter
from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.filters.transform.coordinate import CoordinateTransform
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.sources import AiryLiveSource
from cepf_sdk.transport import WebSocketTransport

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="CEPF USC Pipeline")
    parser.add_argument(
        "--config", "-c",
        default="sensors.json",
        help="センサー設定 JSON ファイル (sensors.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログ出力",
    )
    parser.add_argument(
        "--test-frustum",
        action="store_true",
        help="FrustumFilter のテスト: フィルター前後の詳細統計をログ出力",
    )
    parser.add_argument("--frustum-r-bottom", type=float, default=None,
                        help="FrustumFilter: 底面半径 [m] (デフォルト:R_BOTTOM=1.775)")
    parser.add_argument("--frustum-r-top",    type=float, default=None,
                        help="FrustumFilter: 上面半径 [m] (デフォルト:R_TOP=2.5)")
    parser.add_argument("--frustum-height",   type=float, default=None,
                        help="FrustumFilter: 高さ [m] (デフォルト:HEIGHT=29.0)")
    parser.add_argument("--frustum-z-bottom", type=float, default=None,
                        help="FrustumFilter: 底面 Z 座標 [m] (デフォルト:Z_BOTTOM=0.0)")
    parser.add_argument(
        "--test-ror",
        action="store_true",
        help="RadiusOutlierRemoval のテスト: ノイズ除去を確認",
    )
    parser.add_argument("--ror-radius",         type=float, default=None,
                        help="RoR: 近傍探索半径 [m] (デフォルト:0.3)")
    parser.add_argument("--ror-min-neighbors",  type=int,   default=None,
                        help="RoR: 最少近傍点数 (デフォルト:5)")
    parser.add_argument("--ror-distance-scale", type=float, default=None,
                        help="RoR: 距離適応係数 (デフォルト:0.0)")
    parser.add_argument(
        "--transform",
        action="store_true",
        help="CoordinateTransform を追加: 座標変換",
    )
    parser.add_argument("--transform-azimuth",   type=float, default=None,
                        help="Transform: 方位角回転 [deg]")
    parser.add_argument("--transform-elevation", type=float, default=None,
                        help="Transform: 仰角回転 [deg]")
    parser.add_argument("--transform-tx",        type=float, default=None,
                        help="Transform: X 平行移動 [m]")
    parser.add_argument("--transform-ty",        type=float, default=None,
                        help="Transform: Y 平行移動 [m]")
    parser.add_argument("--transform-tz",        type=float, default=None,
                        help="Transform: Z 平行移動 [m]")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("設定ファイルが見つかりません: %s", config_path)
        logger.info("sensors.json を作成してください。")
        sys.exit(1)

    # JSON から USC を初期化
    usc = UnifiedSenseCloud.from_json(str(config_path))
    logger.info("USC initialized from %s", config_path)

    # フィルターの追加
    if args.transform or args.test_frustum or args.test_ror:
        filters = []
        if args.transform:
            tkw = {}
            if args.transform_azimuth   is not None: tkw["azimuth_deg"]   = args.transform_azimuth
            if args.transform_elevation is not None: tkw["elevation_deg"] = args.transform_elevation
            if args.transform_tx        is not None: tkw["tx"]            = args.transform_tx
            if args.transform_ty        is not None: tkw["ty"]            = args.transform_ty
            if args.transform_tz        is not None: tkw["tz"]            = args.transform_tz
            xform = CoordinateTransform(**tkw)
            filters.append(xform)
            logger.info(
                "CoordinateTransform: azimuth=%.1fdeg, elevation=%.1fdeg, "
                "t=(%.2f, %.2f, %.2f)m",
                xform.azimuth_deg, xform.elevation_deg, xform.tx, xform.ty, xform.tz,
            )
        if args.test_frustum:
            fkw = {}
            if args.frustum_r_bottom is not None: fkw["r_bottom"] = args.frustum_r_bottom
            if args.frustum_r_top    is not None: fkw["r_top"]    = args.frustum_r_top
            if args.frustum_height   is not None: fkw["height"]   = args.frustum_height
            if args.frustum_z_bottom is not None: fkw["z_bottom"] = args.frustum_z_bottom
            frustum = FrustumFilter(**fkw)
            filters.append(frustum)
            logger.info(
                "FrustumFilter: r_bottom=%.3fm, r_top=%.3fm, height=%.1fm, z_bottom=%.1fm",
                frustum.r_bottom, frustum.r_top, frustum.height, frustum.z_bottom,
            )
        if args.test_ror:
            rkw = {}
            if args.ror_radius         is not None: rkw["radius_m"]       = args.ror_radius
            if args.ror_min_neighbors  is not None: rkw["min_neighbors"]  = args.ror_min_neighbors
            if args.ror_distance_scale is not None: rkw["distance_scale"] = args.ror_distance_scale
            ror = RadiusOutlierRemoval(**rkw)
            filters.append(ror)
            logger.info(
                "RadiusOutlierRemoval: radius=%.3fm, min_neighbors=%d, distance_scale=%.3f",
                ror.radius_m, ror.min_neighbors, ror.distance_scale,
            )
        pipeline = FilterPipeline(filters=filters, verbose=True)
    else:
        pipeline = FilterPipeline(
            filters=[
                CylindricalFilter(
                    radius_m=5.0,    # 室内スケール
                    z_min_m=-0.1,    # 床面直下
                    z_max_m=3.0,     # 天井まで
                ),
            ],
            verbose=args.verbose,
        )
    usc.add_filter(lambda frame: _apply_pipeline(frame, pipeline))

    logger.info("Pipeline ready. Waiting for sensor data...")

    transport = None
    ws_loop = None
    # WebSocket 配信を有効にする場合はこの1行を有効に、無効にする場合はコメントアウト
    transport, ws_loop = _start_websocket_server()

    import queue

    frame_queue: queue.Queue = queue.Queue(maxsize=10)

    def _receiver() -> None:
        source = AiryLiveSource(usc, sensor_id="lidar", port=6699, agg_seconds=1.0)
        for frame in source.frames():
            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                logger.warning("frame queue full, dropping frame")

    threading.Thread(target=_receiver, daemon=True).start()
    logger.info("Receiver thread started")

    while True:
        try:
            frame = frame_queue.get(timeout=2.0)
        except queue.Empty:
            continue
        if args.test_frustum:
            log_frustum_stats(frame)
        if args.test_ror:
            log_ror_stats(frame)
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


def log_frustum_stats(frame) -> None:
    """
    FrustumFilter テスト統計ログ。
    フィルタリング結果を出力する。
      残存点数とフィルタ率
      残存点の Z 分布
      残存点の水平距離分布
      残存点の仰角分布
    """
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is None or len(x) == 0:
        logger.warning("[FrustumTest] フレームに点がありません (frame_id=%s)", frame.metadata.frame_id)
        return

    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    z = np.asarray(z, dtype=np.float32)
    n = len(x)

    horiz = np.sqrt(x**2 + y**2)          # 水平距離
    dist3d = np.sqrt(x**2 + y**2 + z**2)  # 3D 距離

    def _pct(arr):
        p = np.percentile(arr, [5, 25, 50, 75, 95])
        return (f"min={np.min(arr):.2f} p5={p[0]:.2f} p25={p[1]:.2f} "
                f"med={p[2]:.2f} p75={p[3]:.2f} p95={p[4]:.2f} max={np.max(arr):.2f}")

    logger.info(
        "[FrustumTest] frame_id=%s  残存点数=%d",
        frame.metadata.frame_id, n,
    )
    logger.info("[FrustumTest]   Z        [m] %s", _pct(z))
    logger.info("[FrustumTest]   水平距離 [m] %s", _pct(horiz))
    logger.info("[FrustumTest]   3D距離   [m] %s", _pct(dist3d))

    # Zヒストグラム
    z_lo, z_hi = float(np.min(z)), float(np.max(z))
    if z_hi > z_lo:
        bins = np.linspace(z_lo, z_hi, 11)
        counts, _ = np.histogram(z, bins=bins)
        hist_str = "  ".join(
            f"{b:.2f}-{e:.2f}m:{c}" for b, e, c in zip(bins, bins[1:], counts)
        )
    else:
        hist_str = f"全点 Z={z_lo:.3f}m"
    logger.info("[FrustumTest]   Z層別点数: %s", hist_str)


def log_ror_stats(frame) -> None:
    """
    RadiusOutlierRemoval テスト用統計ログ。
    ノイズ除去の効き具合を確認する。

    確認ポイント:
      - 残存点数
      - intensity 分布
      - 3D距離分布
    """
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is None or len(x) == 0:
        logger.warning("[RoRTest] フレームに点がありません (frame_id=%s)", frame.metadata.frame_id)
        return

    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    z = np.asarray(z, dtype=np.float32)
    n = len(x)
    dist3d = np.sqrt(x**2 + y**2 + z**2)

    def _pct(arr):
        p = np.percentile(arr, [5, 25, 50, 75, 95])
        return (f"min={np.min(arr):.3f} p5={p[0]:.3f} p25={p[1]:.3f} "
                f"med={p[2]:.3f} p75={p[3]:.3f} p95={p[4]:.3f} max={np.max(arr):.3f}")

    logger.info("[RoRTest] frame_id=%s  残存点数=%d", frame.metadata.frame_id, n)
    logger.info("[RoRTest]   3D距離   [m]  %s", _pct(dist3d))

    intensity = frame.points.get("intensity")
    if intensity is not None:
        intensity = np.asarray(intensity, dtype=np.float32)
        non_nan = intensity[~np.isnan(intensity)]
        if len(non_nan) > 0:
            logger.info("[RoRTest]   intensity     %s", _pct(non_nan))

def process_frame(frame, transport=None, ws_loop=None) -> None:
    """スキャン 1 フレーム分の処理。"""
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
        future = asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
        future.add_done_callback(
            lambda f: logger.debug("WS send done, err=%s", f.exception()) 
            if f.exception() else None
        )

def _apply_pipeline(frame, pipeline: FilterPipeline):
    """FilterPipeline を CepfFrame に適用する"""
    from dataclasses import replace
    result = pipeline.apply(frame.points)
    return replace(frame, points=result.points, point_count=result.count_after)


if __name__ == "__main__":
    main()
