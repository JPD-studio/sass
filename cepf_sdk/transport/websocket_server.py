# cepf_sdk/transport/websocket_server.py
"""WebSocketTransport — asyncio + websockets による点群配信サーバー"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional, Set

import numpy as np
import websockets
from websockets.asyncio.server import ServerConnection, serve

from cepf_sdk.frame import CepfFrame
from cepf_sdk.transport.base import TransportBase

logger = logging.getLogger(__name__)


class WebSocketTransport(TransportBase):
    """
    フィルタリング済み CepfFrame を接続中の全 WebSocket クライアントに
    JSON 形式でブロードキャストするサーバー。

    送信 JSON 形式:
    {
        "frame_id": int,
        "timestamp": float,
        "points": {
            "x": [...],
            "y": [...],
            "z": [...],
            "intensity": [...]   # 存在する場合のみ
        }
    }
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._clients: Set[ServerConnection] = set()
        self._server: Optional[websockets.asyncio.server.Server] = None

    # ------------------------------------------------------------------ #
    # TransportBase 実装                                                   #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """WebSocket サーバーを起動する。"""
        self._server = await serve(self._handler, self.host, self.port)
        logger.info("WebSocketTransport: listening on ws://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        """WebSocket サーバーを停止し、全クライアントを切断する。"""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("WebSocketTransport: stopped")

    async def send(self, frame: CepfFrame) -> None:
        """接続中の全クライアントにフレームを JSON 配信する。"""
        if not self._clients:
            return
        payload = self._frame_to_json(frame)
        dead: Set[ServerConnection] = set()
        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                dead.add(ws)
        self._clients -= dead

    # ------------------------------------------------------------------ #
    # 内部ヘルパー                                                         #
    # ------------------------------------------------------------------ #

    async def _handler(self, websocket: ServerConnection) -> None:
        """新規クライアント接続ハンドラー。切断まで待機する。"""
        self._clients.add(websocket)
        logger.debug("WebSocketTransport: client connected (%d total)", len(self._clients))
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)
            logger.debug("WebSocketTransport: client disconnected (%d total)", len(self._clients))

    @staticmethod
    def _frame_to_json(frame: CepfFrame) -> str:
        pts = frame.points
        points_dict: dict = {}
        for key in ("x", "y", "z", "intensity"):
            if key in pts:
                arr = np.asarray(pts[key], dtype=float)
                points_dict[key] = [
                    None if np.isnan(v) else float(v) for v in arr
                ]
        payload = {
            "frame_id": frame.metadata.frame_id,
            "timestamp": time.time(),
            "points": points_dict,
        }
        return json.dumps(payload)

    @property
    def client_count(self) -> int:
        return len(self._clients)
