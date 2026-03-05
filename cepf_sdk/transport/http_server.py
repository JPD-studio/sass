# cepf_sdk/transport/http_server.py
"""静的ファイル HTTP サーバー — viewer の HTML/JS を配信する"""
from __future__ import annotations

import logging
import os
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

logger = logging.getLogger(__name__)


def serve(directory: str, port: int = 8080, *, daemon: bool = True) -> threading.Thread:
    """
    指定ディレクトリを HTTP で配信するスレッドを起動して返す。

    Parameters
    ----------
    directory:
        配信するルートディレクトリ（絶対パス推奨）。
    port:
        リッスンポート（デフォルト 8080）。
    daemon:
        True の場合、メインスレッド終了時に自動停止する。

    Returns
    -------
    threading.Thread
        起動済みのサーバースレッド。
    """
    directory = os.path.abspath(directory)
    handler = partial(SimpleHTTPRequestHandler, directory=directory)
    server = HTTPServer(("", port), handler)

    def _run() -> None:
        logger.info("HTTP static server: http://0.0.0.0:%d (root=%s)", port, directory)
        server.serve_forever()

    thread = threading.Thread(target=_run, daemon=daemon)
    thread.start()
    return thread
