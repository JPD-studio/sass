# apps/run_pipeline.py
"""パイプラインエントリーポイント"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from cepf_sdk import UnifiedSenseCloud
from cepf_sdk.filters.range.cylindrical import CylindricalFilter
from cepf_sdk.filters.pipeline import FilterPipeline

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

    # ここからセンサーデータの受信・処理ループを実装
    # 例:
    #   for raw_data in receive_udp_packets():
    #       frame = usc.forge("lidar_north", raw_data)
    #       process_frame(frame)


def _apply_pipeline(frame, pipeline: FilterPipeline):
    """FilterPipeline を CepfFrame に適用する"""
    from dataclasses import replace
    result = pipeline.apply(frame.points)
    return replace(frame, points=result.points, point_count=result.count_after)


if __name__ == "__main__":
    main()
