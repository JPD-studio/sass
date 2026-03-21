# apps/run_pipeline.py
"""
SASS パイプラインエントリーポイント

ソース層（PCAP / LiDAR UDP）→ フィルターパイプライン → WebSocket → Viewer

アーキテクチャ:
    Source (OusterPcapSource | AiryLiveSource)
      ↓  Iterator[CepfFrame]
    FilterPipeline (Frustum, RoR, CoordinateTransform, Cylindrical, ...)
      ↓  CepfFrame (filtered)
    WebSocketTransport → Viewer / Detector
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np

from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.range.frustum import FrustumFilter, R_BOTTOM, R_TOP, HEIGHT, Z_BOTTOM
from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.filters.transform.coordinate import CoordinateTransform
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.frame import CepfFrame
from cepf_sdk.transport import WebSocketTransport

logger = logging.getLogger(__name__)


# ================================================================== #
# CLI 引数定義                                                         #
# ================================================================== #

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SASS Pipeline — ソース → フィルター → WebSocket → Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # PCAP 再生 + Frustum フィルター → Viewer
  python apps/run_pipeline.py --use-pcap --pcap pcap/sample.pcap --meta pcap/os1-128-rng19.json --test-frustum

  # Airy LiDAR 実機接続 + 座標変換
  python apps/run_pipeline.py --use-airy-live --config sensors.json --transform --transform-azimuth 45.0
""",
    )

    # ── ソース選択 ──
    src = p.add_argument_group("ソース選択 (いずれか必須)")
    src.add_argument("--use-pcap", action="store_true",
                     help="OusterPcapSource: PCAP ファイルからの再生")
    src.add_argument("--use-airy-live", action="store_true",
                     help="AiryLiveSource: Airy LiDAR UDP 実機接続")

    # ── PCAP ソース設定 ──
    pcap = p.add_argument_group("PCAP ソース設定 (--use-pcap 時)")
    pcap.add_argument("--pcap", type=str, default="pcap/250808sbir_20250808133236_00001.pcap",
                      help="PCAP ファイルパス")
    pcap.add_argument("--meta", type=str, default="pcap/os1-128-rng19.json",
                      help="Ouster メタデータ JSON パス")
    pcap.add_argument("--rate", type=float, default=1.0,
                      help="再生速度倍率 (1.0=実時間, 0=最速)")
    pcap.add_argument("--loop", action="store_true", default=True,
                      help="ループ再生 (デフォルト: 有効)")
    pcap.add_argument("--no-loop", dest="loop", action="store_false",
                      help="ループ再生を無効化")
    pcap.add_argument("--flip-z", action="store_true", default=False,
                      help="Z軸を反転する (下向き設置センサー用、例: OS-DOME 逆さま設置)")

    # ── AiryLive ソース設定 ──
    airy = p.add_argument_group("AiryLive ソース設定 (--use-airy-live 時)")
    airy.add_argument("--config", "-c", default="sensors.json",
                      help="センサー設定 JSON ファイルパス")
    airy.add_argument("--airy-port", type=int, default=6699,
                      help="Airy UDP ポート番号")

    # ── WebSocket 設定 ──
    ws = p.add_argument_group("WebSocket 設定")
    ws.add_argument("--ws-host", default="0.0.0.0", help="WebSocket ホスト")
    ws.add_argument("--ws-port", type=int, default=8765, help="WebSocket ポート")

    # ── Frustum フィルター ──
    fr = p.add_argument_group("FrustumFilter")
    fr.add_argument("--test-frustum", action="store_true",
                    help="FrustumFilter を有効化 + 詳細統計ログ出力")
    fr.add_argument("--frustum-r-bottom", type=float, default=None,
                    help="底面半径 [m] (default: 1.775)")
    fr.add_argument("--frustum-r-top", type=float, default=None,
                    help="上面半径 [m] (default: 2.5)")
    fr.add_argument("--frustum-height", type=float, default=None,
                    help="高さ [m] (default: 32.0)")
    fr.add_argument("--frustum-z-bottom", type=float, default=None,
                    help="底面 Z 座標 [m] (default: -2.0)")

    # ── RadiusOutlierRemoval ──
    ror = p.add_argument_group("RadiusOutlierRemoval")
    ror.add_argument("--test-ror", action="store_true",
                     help="RoR を有効化 + 詳細統計ログ出力")
    ror.add_argument("--ror-radius", type=float, default=None,
                     help="近傍探索半径 [m] (default: 0.3)")
    ror.add_argument("--ror-min-neighbors", type=int, default=None,
                     help="最少近傍点数 (default: 5)")
    ror.add_argument("--ror-distance-scale", type=float, default=None,
                     help="距離適応係数 (default: 0.0)")

    # ── CoordinateTransform ──
    tr = p.add_argument_group("CoordinateTransform")
    tr.add_argument("--transform", action="store_true",
                    help="座標変換フィルターを有効化")
    tr.add_argument("--transform-azimuth", type=float, default=None,
                    help="方位角回転 [deg]")
    tr.add_argument("--transform-elevation", type=float, default=None,
                    help="仰角回転 [deg]")
    tr.add_argument("--transform-tx", type=float, default=None,
                    help="X 平行移動 [m]")
    tr.add_argument("--transform-ty", type=float, default=None,
                    help="Y 平行移動 [m]")
    tr.add_argument("--transform-tz", type=float, default=None,
                    help="Z 平行移動 [m]")

    # ── 一般設定 ──
    p.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")

    return p


# ================================================================== #
# フィルターパイプライン構築                                             #
# ================================================================== #

def _build_pipeline(args) -> FilterPipeline:
    """コマンドライン引数に基づいてフィルターパイプラインを構築する。"""
    filters = []

    # FrustumFilter
    if args.test_frustum:
        r_bottom = args.frustum_r_bottom if args.frustum_r_bottom is not None else R_BOTTOM
        r_top = args.frustum_r_top if args.frustum_r_top is not None else R_TOP
        height = args.frustum_height if args.frustum_height is not None else HEIGHT
        z_bottom = args.frustum_z_bottom if args.frustum_z_bottom is not None else Z_BOTTOM
        filters.append(FrustumFilter(r_bottom=r_bottom, r_top=r_top,
                                      height=height, z_bottom=z_bottom))
        logger.info("FrustumFilter: r_bottom=%.3f r_top=%.3f height=%.1f z_bottom=%.1f",
                     r_bottom, r_top, height, z_bottom)

    # RadiusOutlierRemoval
    if args.test_ror:
        radius = args.ror_radius if args.ror_radius is not None else 0.3
        min_neighbors = args.ror_min_neighbors if args.ror_min_neighbors is not None else 5
        distance_scale = args.ror_distance_scale if args.ror_distance_scale is not None else 0.0
        filters.append(RadiusOutlierRemoval(radius_m=radius, min_neighbors=min_neighbors,
                                            distance_scale=distance_scale))
        logger.info("RadiusOutlierRemoval: radius=%.3f min_neighbors=%d distance_scale=%.3f",
                     radius, min_neighbors, distance_scale)

    # CoordinateTransform
    if args.transform:
        azimuth = args.transform_azimuth if args.transform_azimuth is not None else 0.0
        elevation = args.transform_elevation if args.transform_elevation is not None else 0.0
        tx = args.transform_tx if args.transform_tx is not None else 0.0
        ty = args.transform_ty if args.transform_ty is not None else 0.0
        tz = args.transform_tz if args.transform_tz is not None else 0.0
        filters.append(CoordinateTransform(azimuth_deg=azimuth, elevation_deg=elevation,
                                           tx_m=tx, ty_m=ty, tz_m=tz))
        logger.info("CoordinateTransform: azimuth=%.2f elevation=%.2f tx=%.3f ty=%.3f tz=%.3f",
                     azimuth, elevation, tx, ty, tz)

    # デフォルト: CylindricalFilter (広域クリッピング)
    filters.append(CylindricalFilter(radius_m=50.0, z_min_m=-2.0, z_max_m=30.0))

    pipeline = FilterPipeline(filters=filters, verbose=args.verbose)
    logger.info("FilterPipeline: %d フィルター構成", len(filters))
    return pipeline


# ================================================================== #
# ソース生成                                                            #
# ================================================================== #

def _create_source(args):
    """コマンドライン引数に基づいてデータソースを生成する。"""
    if args.use_pcap:
        from cepf_sdk.sources import OusterPcapSource

        pcap_path = Path(args.pcap)
        meta_path = Path(args.meta)
        if not pcap_path.exists():
            logger.error("PCAP が見つかりません: %s", pcap_path)
            sys.exit(1)
        if not meta_path.exists():
            logger.error("メタ JSON が見つかりません: %s", meta_path)
            sys.exit(1)

        logger.info("ソース: OusterPcapSource (PCAP=%s, rate=%.1f, loop=%s, flip_z=%s)",
                     pcap_path.name, args.rate, args.loop, args.flip_z)
        return OusterPcapSource(pcap_path, meta_path,
                                rate=args.rate, loop=args.loop, flip_z=args.flip_z)

    elif args.use_airy_live:
        from cepf_sdk import UnifiedSenseCloud
        from cepf_sdk.sources import AiryLiveSource

        config_path = Path(args.config)
        if not config_path.exists():
            logger.error("設定ファイルが見つかりません: %s", config_path)
            logger.info("sensors.example.json をコピーして sensors.json を作成してください。")
            sys.exit(1)

        usc = UnifiedSenseCloud.from_json(str(config_path))
        logger.info("ソース: AiryLiveSource (port=%d, config=%s)", args.airy_port, config_path)
        return AiryLiveSource(usc, sensor_id="lidar",
                              port=args.airy_port, agg_seconds=1.0)

    else:
        logger.error("ソースが指定されていません。--use-pcap または --use-airy-live を指定してください。")
        sys.exit(1)


# ================================================================== #
# WebSocket サーバー                                                    #
# ================================================================== #

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


# ================================================================== #
# フレーム処理                                                          #
# ================================================================== #

def _apply_pipeline(frame: CepfFrame, pipeline: FilterPipeline) -> CepfFrame:
    """FilterPipeline を CepfFrame に適用し、フィルタ済みフレームを返す。"""
    result = pipeline.apply(frame.points)
    return replace(frame, points=result.points, point_count=result.count_after)


def _process_frame(frame: CepfFrame, transport, ws_loop) -> None:
    """フレームを WebSocket で配信する。"""
    if transport is not None and ws_loop is not None:
        future = asyncio.run_coroutine_threadsafe(transport.send(frame), ws_loop)
        future.add_done_callback(
            lambda f: logger.debug("WS send done, err=%s", f.exception())
            if f.exception() else None
        )


def _log_frame_stats(frame: CepfFrame) -> None:
    """フレームの基本統計をログ出力する。"""
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is not None and len(x) > 0:
        r = np.sqrt(np.asarray(x)**2 + np.asarray(y)**2 + np.asarray(z)**2)
        p = np.percentile(r, [5, 25, 50, 75, 95])
        logger.info(
            "frame %d: points=%d  range min=%.1f p5=%.1f med=%.1f p95=%.1f max=%.1f [m]",
            frame.metadata.frame_id, frame.point_count, float(np.min(r)),
            p[0], p[2], p[4], float(np.max(r))
        )


def _log_frustum_stats(frame: CepfFrame) -> None:
    """FrustumFilter テスト統計ログ。"""
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is None or len(x) == 0:
        logger.warning("[FrustumTest] 点なし (frame_id=%s)", frame.metadata.frame_id)
        return

    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    z = np.asarray(z, dtype=np.float32)
    n = len(x)

    horiz = np.sqrt(x**2 + y**2)
    dist3d = np.sqrt(x**2 + y**2 + z**2)

    def _pct(arr):
        p = np.percentile(arr, [5, 25, 50, 75, 95])
        return (f"min={np.min(arr):.2f} p5={p[0]:.2f} p25={p[1]:.2f} "
                f"med={p[2]:.2f} p75={p[3]:.2f} p95={p[4]:.2f} max={np.max(arr):.2f}")

    logger.info("[FrustumTest] frame_id=%s 残存点数=%d", frame.metadata.frame_id, n)
    logger.info("[FrustumTest]   Z        [m] %s", _pct(z))
    logger.info("[FrustumTest]   水平距離 [m] %s", _pct(horiz))
    logger.info("[FrustumTest]   3D距離   [m] %s", _pct(dist3d))

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


def _log_ror_stats(frame: CepfFrame) -> None:
    """RadiusOutlierRemoval テスト統計ログ。"""
    x = frame.points.get("x")
    y = frame.points.get("y")
    z = frame.points.get("z")
    if x is None or len(x) == 0:
        logger.warning("[RoRTest] 点なし (frame_id=%s)", frame.metadata.frame_id)
        return

    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    z = np.asarray(z, dtype=np.float32)
    dist3d = np.sqrt(x**2 + y**2 + z**2)

    def _pct(arr):
        p = np.percentile(arr, [5, 25, 50, 75, 95])
        return (f"min={np.min(arr):.3f} p5={p[0]:.3f} p25={p[1]:.3f} "
                f"med={p[2]:.3f} p75={p[3]:.3f} p95={p[4]:.3f} max={np.max(arr):.3f}")

    logger.info("[RoRTest] frame_id=%s 残存点数=%d", frame.metadata.frame_id, len(x))
    logger.info("[RoRTest]   3D距離   [m]  %s", _pct(dist3d))

    intensity = frame.points.get("intensity")
    if intensity is not None:
        intensity = np.asarray(intensity, dtype=np.float32)
        non_nan = intensity[~np.isnan(intensity)]
        if len(non_nan) > 0:
            logger.info("[RoRTest]   intensity     %s", _pct(non_nan))


# ================================================================== #
# メインエントリーポイント                                               #
# ================================================================== #

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 1. フィルターパイプライン構築
    pipeline = _build_pipeline(args)

    # 2. データソース生成
    source = _create_source(args)

    # 3. WebSocket サーバー起動
    transport, ws_loop = _start_websocket_server(host=args.ws_host, port=args.ws_port)

    # 4. メインループ — ソースからフレームを取得 → フィルター → WebSocket 配信
    logger.info("パイプライン開始: ソース → フィルター → WebSocket 配信")
    for frame in source.frames():
        # フィルター適用
        filtered = _apply_pipeline(frame, pipeline)

        # 統計ログ (テストモード)
        if args.test_frustum:
            _log_frustum_stats(filtered)
        if args.test_ror:
            _log_ror_stats(filtered)

        # フレーム統計 (20フレームごと)
        if filtered.metadata.frame_id % 20 == 0:
            _log_frame_stats(filtered)

        # WebSocket 配信
        _process_frame(filtered, transport, ws_loop)


if __name__ == "__main__":
    main()
