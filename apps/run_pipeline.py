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
import json
import logging
import sys
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np

import warnings

from cepf_sdk.filters.range.box import BoxFilter
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.range.frustum import FrustumFilter, R_BOTTOM, R_TOP, HEIGHT, Z_BOTTOM
from cepf_sdk.filters.range.polygon import PolygonFilter
from cepf_sdk.filters.range.spherical import SphericalFilter
from cepf_sdk.filters.statistical.ror import RadiusOutlierRemoval
from cepf_sdk.filters.transform.axis_sign import AxisSignFilter
from cepf_sdk.filters.transform.coordinate import CoordinateTransform
from cepf_sdk.filters.pipeline import FilterPipeline
from cepf_sdk.frame import CepfFrame
from cepf_sdk.transport import WebSocketTransport

logger = logging.getLogger(__name__)

# config/sass.json のパス（apps/run_pipeline.py から見て ../config/sass.json）
_SASS_JSON: Path = Path(__file__).resolve().parent.parent / "config" / "sass.json"


def _load_sass_config() -> dict:
    """config/sass.json を読み込む。存在しない・読み込み失敗時は空 dict を返す。"""
    try:
        if _SASS_JSON.exists():
            return json.loads(_SASS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("config/sass.json の読み込みに失敗しました（フォールバック値を使用）: %s", e)
    return {}


def _load_axis_sign() -> tuple:
    """config/sass.json の enabled センサーの axis_sign を読み込む。

    複数センサーが enabled の場合、全センサーで axis_sign が一致しているかチェックし、
    不一致ならログ警告を出した上で最初の enabled センサーの値を使用する。
    読み込み失敗時は (1,1,1) を返す。
    """
    try:
        data = json.loads(_SASS_JSON.read_text(encoding="utf-8"))
        signs = []
        for s in data.get("sensors", []):
            if s.get("enabled"):
                ax = s.get("config", {}).get("axis_sign", {})
                x, y, z = ax.get("x", 1), ax.get("y", 1), ax.get("z", 1)
                # 有効値チェック: 1 または -1 のみ許可
                for name, val in (("x", x), ("y", y), ("z", z)):
                    if val not in (1, -1):
                        logger.warning("axis_sign.%s = %s は無効な値（1 か -1 のみ有効）。1 に補正。", name, val)
                        if name == "x": x = 1
                        elif name == "y": y = 1
                        else: z = 1
                signs.append((x, y, z))
        if not signs:
            return (1, 1, 1)
        if len(set(signs)) > 1:
            logger.warning(
                "複数の enabled センサーで axis_sign が異なります: %s — 最初の値 %s を使用",
                signs, signs[0]
            )
        return signs[0]
    except Exception:
        return (1, 1, 1)


# ================================================================== #
# CLI 引数定義                                                         #
# ================================================================== #

def _build_parser() -> argparse.ArgumentParser:
    # config/sass.json を読み込み（失敗時は空 dict。フォールバック値を使用）
    sass_cfg = _load_sass_config()
    _filters = sass_cfg.get("filters", {})
    _frustum = _filters.get("frustum", {})
    _ror = _filters.get("ror", {})

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
                      help="[非推奨] config/sass.json の axis_sign を使用してください")

    # ── AiryLive ソース設定 ──
    airy = p.add_argument_group("AiryLive ソース設定 (--use-airy-live 時)")
    airy.add_argument("--config", "-c", default=str(_SASS_JSON),
                      help="AiryLiveSource 用センサー設定 JSON ファイルパス（--use-airy-live 時のみ使用）")
    airy.add_argument("--airy-port", type=int, default=6699,
                      help="Airy UDP ポート番号")

    # ── WebSocket 設定 ──
    ws = p.add_argument_group("WebSocket 設定")
    ws.add_argument("--ws-host", default="0.0.0.0", help="WebSocket ホスト")
    ws.add_argument("--ws-port", type=int, default=8765, help="WebSocket ポート")

    # ── Frustum フィルター（フォールバック: frustum.py モジュール定数）──
    fr = p.add_argument_group("FrustumFilter")
    fr.add_argument("--test-frustum", action="store_true",
                    help="FrustumFilter を有効化 + 詳細統計ログ出力")
    fr.add_argument("--frustum-r-bottom", type=float,
                    default=_frustum.get("r_bottom", R_BOTTOM),
                    help="底面半径 [m] (default: %.3f)" % _frustum.get("r_bottom", R_BOTTOM))
    fr.add_argument("--frustum-r-top", type=float,
                    default=_frustum.get("r_top", R_TOP),
                    help="上面半径 [m] (default: %.3f)" % _frustum.get("r_top", R_TOP))
    fr.add_argument("--frustum-height", type=float,
                    default=_frustum.get("height", HEIGHT),
                    help="高さ [m] (default: %.1f)" % _frustum.get("height", HEIGHT))
    fr.add_argument("--frustum-z-bottom", type=float,
                    default=_frustum.get("z_bottom", Z_BOTTOM),
                    help="底面 Z 座標 [m] (default: %.1f)" % _frustum.get("z_bottom", Z_BOTTOM))

    # ── RadiusOutlierRemoval（フォールバック: ハードコード値）──
    ror_grp = p.add_argument_group("RadiusOutlierRemoval")
    ror_grp.add_argument("--test-ror", action="store_true",
                     help="RoR を有効化 + 詳細統計ログ出力")
    ror_grp.add_argument("--ror-radius", type=float,
                     default=_ror.get("radius", 0.3),
                     help="近傍探索半径 [m] (default: %.1f)" % _ror.get("radius", 0.3))
    ror_grp.add_argument("--ror-min-neighbors", type=int,
                     default=_ror.get("min_neighbors", 5),
                     help="最少近傍点数 (default: %d)" % _ror.get("min_neighbors", 5))
    ror_grp.add_argument("--ror-distance-scale", type=float,
                     default=_ror.get("distance_scale", 0.0),
                     help="距離適応係数 (default: %.1f)" % _ror.get("distance_scale", 0.0))

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

    # ── SphericalFilter ──
    _sph = _filters.get("spherical", {})
    sph = p.add_argument_group("SphericalFilter")
    sph.add_argument("--spherical", action="store_true",
                     help="SphericalFilter を有効化")
    sph.add_argument("--spherical-radius", type=float,
                     default=_sph.get("radius", 30.0),
                     help="球の半径 [m] (default: %.1f)" % _sph.get("radius", 30.0))
    sph.add_argument("--spherical-cx", type=float,
                     default=_sph.get("cx", 0.0),
                     help="中心 X [m] (default: %.1f)" % _sph.get("cx", 0.0))
    sph.add_argument("--spherical-cy", type=float,
                     default=_sph.get("cy", 0.0),
                     help="中心 Y [m] (default: %.1f)" % _sph.get("cy", 0.0))
    sph.add_argument("--spherical-cz", type=float,
                     default=_sph.get("cz", 0.0),
                     help="中心 Z [m] (default: %.1f)" % _sph.get("cz", 0.0))
    sph.add_argument("--spherical-invert", action="store_true",
                     default=_sph.get("invert", False),
                     help="範囲を反転（球外部を残す）")

    # ── BoxFilter ──
    _box = _filters.get("box", {})
    box = p.add_argument_group("BoxFilter")
    box.add_argument("--box", action="store_true",
                     help="BoxFilter を有効化")
    box.add_argument("--box-x-min", type=float,
                     default=_box.get("x_min", -25.0),
                     help="X 下限 [m] (default: %.1f)" % _box.get("x_min", -25.0))
    box.add_argument("--box-x-max", type=float,
                     default=_box.get("x_max", 25.0),
                     help="X 上限 [m] (default: %.1f)" % _box.get("x_max", 25.0))
    box.add_argument("--box-y-min", type=float,
                     default=_box.get("y_min", -25.0),
                     help="Y 下限 [m] (default: %.1f)" % _box.get("y_min", -25.0))
    box.add_argument("--box-y-max", type=float,
                     default=_box.get("y_max", 25.0),
                     help="Y 上限 [m] (default: %.1f)" % _box.get("y_max", 25.0))
    box.add_argument("--box-z-min", type=float,
                     default=_box.get("z_min", -20.0),
                     help="Z 下限 [m] (default: %.1f)" % _box.get("z_min", -20.0))
    box.add_argument("--box-z-max", type=float,
                     default=_box.get("z_max", 30.0),
                     help="Z 上限 [m] (default: %.1f)" % _box.get("z_max", 30.0))
    box.add_argument("--box-invert", action="store_true",
                     default=_box.get("invert", False),
                     help="範囲を反転（直方体外部を残す）")

    # ── PolygonFilter ──
    _poly = _filters.get("polygon", {})
    poly = p.add_argument_group("PolygonFilter")
    poly.add_argument("--polygon", action="store_true",
                      help="PolygonFilter を有効化")
    poly.add_argument("--polygon-z-min", type=float,
                      default=_poly.get("z_min", -20.0),
                      help="Z 下限 [m] (default: %.1f)" % _poly.get("z_min", -20.0))
    poly.add_argument("--polygon-z-max", type=float,
                      default=_poly.get("z_max", 30.0),
                      help="Z 上限 [m] (default: %.1f)" % _poly.get("z_max", 30.0))
    poly.add_argument("--polygon-invert", action="store_true",
                      default=_poly.get("invert", False),
                      help="範囲を反転（多角形外部を残す）")

    # ── 一般設定 ──
    p.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")

    return p


# ================================================================== #
# フィルターパイプライン構築                                             #
# ================================================================== #

def _build_pipeline(args) -> tuple:
    """コマンドライン引数と config/sass.json に基づいてフィルターパイプラインを構築する。

    有効化の優先順位（高→低）:
        1. CLI フラグ（--test-frustum 等）  … 強制 ON（config を上書き）
        2. config/sass.json の enabled フラグ … 通常の ON/OFF 制御
        3. デフォルト値                       … 未記載時のフォールバック

    Returns:
        (FilterPipeline, dict)  — パイプラインと有効フラグ辞書
        有効フラグ辞書キー: "frustum", "ror", "coordinate_transform", "cylindrical"
    """
    filters = []

    # config/sass.json の filters セクションを一括読み込み
    _ftrs = _load_sass_config().get("filters", {})
    _frustum = _ftrs.get("frustum", {})
    _ror_cfg  = _ftrs.get("ror", {})
    _coord    = _ftrs.get("coordinate_transform", {})
    _cyl      = _ftrs.get("cylindrical", {})
    _sph_cfg  = _ftrs.get("spherical", {})
    _box_cfg  = _ftrs.get("box", {})
    _poly_cfg = _ftrs.get("polygon", {})

    # ── ① AxisSignFilter（フィルター先頭に自動注入、sensors[].config.axis_sign から）──
    ax = _load_axis_sign()

    # --flip-z 廃止処理（DeprecationWarning + 強制 z_sign=-1）
    if args.flip_z:
        warnings.warn(
            "--flip-z は非推奨です。config/sass.json の sensors[].config.axis_sign を使用してください。",
            DeprecationWarning,
            stacklevel=2,
        )
        if ax[2] == -1:
            logger.warning("config/sass.json の axis_sign.z=-1 と --flip-z の同時指定は二重反転になります。"
                           "--flip-z を優先して z_sign=-1 を適用します。")
        ax = (ax[0], ax[1], -1)

    if ax != (1, 1, 1):
        filters.append(AxisSignFilter(x_sign=ax[0], y_sign=ax[1], z_sign=ax[2]))
        logger.info("AxisSignFilter: x=%+d y=%+d z=%+d", *ax)

    # ── ② FrustumFilter（CLI フラグ OR config.enabled）──
    frustum_enabled = args.test_frustum or _frustum.get("enabled", False)
    if frustum_enabled:
        filters.append(FrustumFilter(
            r_bottom=args.frustum_r_bottom,
            r_top=args.frustum_r_top,
            height=args.frustum_height,
            z_bottom=args.frustum_z_bottom,
        ))
        logger.info("FrustumFilter: r_bottom=%.3f r_top=%.3f height=%.1f z_bottom=%.1f",
                     args.frustum_r_bottom, args.frustum_r_top,
                     args.frustum_height, args.frustum_z_bottom)

    # ── ③ RadiusOutlierRemoval（CLI フラグ OR config.enabled）──
    ror_enabled = args.test_ror or _ror_cfg.get("enabled", False)
    if ror_enabled:
        radius = args.ror_radius
        min_neighbors = args.ror_min_neighbors
        distance_scale = args.ror_distance_scale
        filters.append(RadiusOutlierRemoval(radius_m=radius, min_neighbors=min_neighbors,
                                            distance_scale=distance_scale))
        logger.info("RadiusOutlierRemoval: radius=%.3f min_neighbors=%d distance_scale=%.3f",
                     radius, min_neighbors, distance_scale)

    # ── ④ CoordinateTransform（CLI フラグ OR config.enabled）──
    # CLI 引数が None の場合は config 値を使用（config も未設定なら 0.0）
    coord_enabled = args.transform or _coord.get("enabled", False)
    if coord_enabled:
        azimuth   = args.transform_azimuth   if args.transform_azimuth   is not None else _coord.get("azimuth",   0.0)
        elevation = args.transform_elevation if args.transform_elevation is not None else _coord.get("elevation", 0.0)
        tx = args.transform_tx if args.transform_tx is not None else _coord.get("tx", 0.0)
        ty = args.transform_ty if args.transform_ty is not None else _coord.get("ty", 0.0)
        tz = args.transform_tz if args.transform_tz is not None else _coord.get("tz", 0.0)
        filters.append(CoordinateTransform(azimuth_deg=azimuth, elevation_deg=elevation,
                                           tx_m=tx, ty_m=ty, tz_m=tz))
        logger.info("CoordinateTransform: azimuth=%.2f elevation=%.2f tx=%.3f ty=%.3f tz=%.3f",
                     azimuth, elevation, tx, ty, tz)

    # ── ⑤ CylindricalFilter（config.enabled、デフォルト True）──
    cyl_enabled = _cyl.get("enabled", True)
    cyl_radius  = _cyl.get("radius", 50.0)
    cyl_z_min   = _cyl.get("z_min",  -2.0)
    cyl_z_max   = _cyl.get("z_max",  30.0)

    # ⚠ 競合チェック: FrustumFilter z_bottom < CylindricalFilter z_min の場合に警告
    if frustum_enabled and cyl_enabled and cyl_z_min > args.frustum_z_bottom:
        logger.warning(
            "設定の競合: FrustumFilter z_bottom=%.1f < CylindricalFilter z_min=%.1f\n"
            "  → FrustumFilter が z=%.1f まで通した点を CylindricalFilter が z=%.1f で切り捨てます。\n"
            "  → 解決策: config/sass.json の filters.cylindrical.z_min を %.1f 以下に変更してください。",
            args.frustum_z_bottom, cyl_z_min,
            args.frustum_z_bottom, cyl_z_min,
            args.frustum_z_bottom,
        )

    if cyl_enabled:
        filters.append(CylindricalFilter(radius_m=cyl_radius, z_min_m=cyl_z_min, z_max_m=cyl_z_max))

    # ── ⑥ SphericalFilter（CLI フラグ OR config.enabled）──
    sph_enabled = args.spherical or _sph_cfg.get("enabled", False)
    if sph_enabled:
        filters.append(SphericalFilter(
            radius_m=args.spherical_radius,
            cx=args.spherical_cx,
            cy=args.spherical_cy,
            cz=args.spherical_cz,
            invert=args.spherical_invert,
        ))
        logger.info("SphericalFilter: radius=%.1f cx=%.1f cy=%.1f cz=%.1f invert=%s",
                     args.spherical_radius, args.spherical_cx, args.spherical_cy,
                     args.spherical_cz, args.spherical_invert)

    # ── ⑦ BoxFilter（CLI フラグ OR config.enabled）──
    box_enabled = args.box or _box_cfg.get("enabled", False)
    if box_enabled:
        filters.append(BoxFilter(
            x_min=args.box_x_min, x_max=args.box_x_max,
            y_min=args.box_y_min, y_max=args.box_y_max,
            z_min=args.box_z_min, z_max=args.box_z_max,
            invert=args.box_invert,
        ))
        logger.info("BoxFilter: x=[%.1f, %.1f] y=[%.1f, %.1f] z=[%.1f, %.1f] invert=%s",
                     args.box_x_min, args.box_x_max,
                     args.box_y_min, args.box_y_max,
                     args.box_z_min, args.box_z_max, args.box_invert)

    # ── ⑧ PolygonFilter（CLI フラグ OR config.enabled）──
    # 頂点リストは config/sass.json のみから読み込む（CLI での多角形指定は非実用的なため）
    poly_enabled = args.polygon or _poly_cfg.get("enabled", False)
    if poly_enabled:
        vertices = _poly_cfg.get("vertices", [])
        if len(vertices) < 3:
            logger.warning(
                "PolygonFilter: config/sass.json の filters.polygon.vertices に "
                "3頂点以上を指定してください（現在 %d 頂点）。フィルターをスキップします。",
                len(vertices)
            )
            poly_enabled = False
        else:
            poly_verts = [tuple(v) for v in vertices]
            filters.append(PolygonFilter(
                polygon=poly_verts,
                z_min=args.polygon_z_min,
                z_max=args.polygon_z_max,
                invert=args.polygon_invert,
            ))
            logger.info("PolygonFilter: %d頂点 z=[%.1f, %.1f] invert=%s",
                         len(poly_verts), args.polygon_z_min, args.polygon_z_max, args.polygon_invert)

    pipeline = FilterPipeline(filters=filters, verbose=args.verbose)
    logger.info("FilterPipeline: %d フィルター構成", len(filters))

    enabled_flags = {
        "frustum":              frustum_enabled,
        "ror":                  ror_enabled,
        "coordinate_transform": coord_enabled,
        "cylindrical":          cyl_enabled,
        "spherical":            sph_enabled,
        "box":                  box_enabled,
        "polygon":              poly_enabled,
    }
    return pipeline, enabled_flags


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

        logger.info("ソース: OusterPcapSource (PCAP=%s, rate=%.1f, loop=%s)",
                     pcap_path.name, args.rate, args.loop)
        return OusterPcapSource(pcap_path, meta_path,
                                rate=args.rate, loop=args.loop)

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
    ready = threading.Event()
    start_error: list = [None]

    def _thread() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(transport.start())
        except Exception as exc:
            start_error[0] = exc
            ready.set()
            return  # loop.run_forever() には進まない
        ready.set()   # 成功シグナル
        loop.run_forever()

    threading.Thread(target=_thread, daemon=True).start()

    if not ready.wait(timeout=10):
        logger.error("WebSocket サーバーの起動がタイムアウトしました (10s)")
        sys.exit(1)
    if start_error[0] is not None:
        logger.error(
            "WebSocket サーバーの起動に失敗しました: %s\n"
            "  → ポート %d が既に使用中の可能性があります。\n"
            "  → 解決策: ./start.sh --stop を実行して旧プロセスを終了してください。",
            start_error[0], port,
        )
        sys.exit(1)

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
    pipeline, enabled_flags = _build_pipeline(args)

    # 2. データソース生成
    source = _create_source(args)

    # 3. WebSocket サーバー起動
    transport, ws_loop = _start_websocket_server(host=args.ws_host, port=args.ws_port)

    # 3b. effective config を WS ブロードキャスト（ワイヤーフレーム同期用）
    _ftrs = _load_sass_config().get("filters", {})
    _ftrs_frustum = _ftrs.get("frustum", {})
    _ftrs_cyl     = _ftrs.get("cylindrical", {})
    _ftrs_sph     = _ftrs.get("spherical", {})
    _ftrs_box     = _ftrs.get("box", {})
    _ftrs_poly    = _ftrs.get("polygon", {})
    effective_config = {
        "type": "filter_config",
        "frustum": {
            "r_bottom": args.frustum_r_bottom,
            "r_top": args.frustum_r_top,
            "height": args.frustum_height,
            "z_bottom": args.frustum_z_bottom,
            "active": enabled_flags["frustum"],
            "show_wireframe": _ftrs_frustum.get("wireframe", True),
        },
        "cylindrical": {
            "radius": _ftrs_cyl.get("radius", 50.0),
            "z_min": _ftrs_cyl.get("z_min", -20.0),
            "z_max": _ftrs_cyl.get("z_max", 30.0),
            "active": enabled_flags["cylindrical"],
            "show_wireframe": _ftrs_cyl.get("wireframe", False),
        },
        "spherical": {
            "radius": _ftrs_sph.get("radius", 30.0),
            "cx": _ftrs_sph.get("cx", 0.0),
            "cy": _ftrs_sph.get("cy", 0.0),
            "cz": _ftrs_sph.get("cz", 0.0),
            "active": enabled_flags["spherical"],
            "show_wireframe": _ftrs_sph.get("wireframe", False),
        },
        "box": {
            "x_min": _ftrs_box.get("x_min", -25.0),
            "x_max": _ftrs_box.get("x_max",  25.0),
            "y_min": _ftrs_box.get("y_min", -25.0),
            "y_max": _ftrs_box.get("y_max",  25.0),
            "z_min": _ftrs_box.get("z_min", -20.0),
            "z_max": _ftrs_box.get("z_max",  30.0),
            "active": enabled_flags["box"],
            "show_wireframe": _ftrs_box.get("wireframe", False),
        },
        "polygon": {
            "vertices": _ftrs_poly.get("vertices", []),
            "z_min": _ftrs_poly.get("z_min", -20.0),
            "z_max": _ftrs_poly.get("z_max",  30.0),
            "active": enabled_flags["polygon"],
            "show_wireframe": _ftrs_poly.get("wireframe", False),
        },
    }
    asyncio.run_coroutine_threadsafe(
        transport.broadcast_raw(json.dumps(effective_config)), ws_loop
    )

    # 4. メインループ — ソースからフレームを取得 → フィルター → WebSocket 配信
    logger.info("パイプライン開始: ソース → フィルター → WebSocket 配信")
    for frame in source.frames():
        # フィルター適用
        filtered = _apply_pipeline(frame, pipeline)

        # 統計ログ (テストモード: CLI フラグ OR config.enabled で有効)
        if enabled_flags["frustum"]:
            _log_frustum_stats(filtered)
        if enabled_flags["ror"]:
            _log_ror_stats(filtered)

        # フレーム統計 (20フレームごと)
        if filtered.metadata.frame_id % 20 == 0:
            _log_frame_stats(filtered)

        # WebSocket 配信
        _process_frame(filtered, transport, ws_loop)


if __name__ == "__main__":
    main()
