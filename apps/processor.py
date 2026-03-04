# apps_py/processor.py
"""後段処理ロジック"""
from __future__ import annotations

import logging
from typing import Any, Callable, List

from cepf_sdk.frame import CepfFrame

logger = logging.getLogger(__name__)


class FrameProcessor:
    """
    CepfFrame の後段処理を管理するクラス。

    使い方:
        proc = FrameProcessor()
        proc.add_handler(save_to_file)
        proc.add_handler(visualize)
        proc.process(frame)
    """

    def __init__(self) -> None:
        self._handlers: List[Callable[[CepfFrame], Any]] = []

    def add_handler(self, handler: Callable[[CepfFrame], Any]) -> FrameProcessor:
        """ハンドラーを追加"""
        self._handlers.append(handler)
        return self

    def process(self, frame: CepfFrame) -> None:
        """全ハンドラーにフレームを渡す"""
        for handler in self._handlers:
            try:
                handler(frame)
            except Exception:
                logger.exception("Handler %s failed", handler.__name__)
