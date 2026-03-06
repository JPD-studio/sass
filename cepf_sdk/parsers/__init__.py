# cepf_sdk/parsers/__init__.py
"""パーサー群 — 遅延インポートによるパーサー登録マップ"""
from __future__ import annotations

import importlib
from typing import Dict, Type

from cepf_sdk.parsers.base import RawDataParser

# パーサー名 → "module.ClassName" のマップ（遅延インポート用）
_PARSER_MAP: Dict[str, str] = {
    "robosense_airy": "cepf_sdk.parsers.robosense_airy.RoboSenseAiryParser",
    "ouster_dome128": "cepf_sdk.parsers.ouster_dome128.OusterDome128Parser",
    "ouster":         "cepf_sdk.parsers.ouster.OusterLidarParser",
    "velodyne":       "cepf_sdk.parsers.velodyne.VelodyneLidarParser",
    "ti_radar":       "cepf_sdk.parsers.ti_radar.TIRadarParser",
    "continental":    "cepf_sdk.parsers.continental.ContinentalRadarParser",
}


def get_parser_class(name: str) -> Type[RawDataParser]:
    """パーサー名から遅延インポートでクラスを取得する。"""
    dotted = _PARSER_MAP.get(name)
    if dotted is None:
        from cepf_sdk.errors import ParserNotFoundError
        raise ParserNotFoundError(f"Unknown parser: {name!r}. Available: {list(_PARSER_MAP.keys())}")
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def register_parser(name: str, dotted_path: str) -> None:
    """カスタムパーサーを登録する。"""
    _PARSER_MAP[name] = dotted_path


__all__ = ["RawDataParser", "get_parser_class", "register_parser"]
