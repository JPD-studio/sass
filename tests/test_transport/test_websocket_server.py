# tests/test_transport/test_websocket_server.py
"""WebSocketTransport の統合テスト"""
from __future__ import annotations

import asyncio
import json
import time

import numpy as np
import pytest
import websockets

from cepf_sdk.transport.websocket_server import WebSocketTransport
from cepf_sdk.frame import CepfFrame, CepfMetadata
from cepf_sdk.enums import CoordinateMode, CoordinateSystem, SensorType


# --------------------------------------------------------------------------- #
# テスト用 CepfFrame ファクトリー                                              #
# --------------------------------------------------------------------------- #

def _make_frame(frame_id: int = 1) -> CepfFrame:
    metadata = CepfMetadata(
        timestamp_utc="2026-03-04T00:00:00+00:00",
        frame_id=frame_id,
        coordinate_system=CoordinateSystem.SENSOR_LOCAL.value,
        coordinate_mode=CoordinateMode.CARTESIAN.value,
        units={"x": "m", "y": "m", "z": "m"},
        sensor={"sensor_type": SensorType.LIDAR.value},
    )
    return CepfFrame(
        format="CEPF",
        version="1.4.0",
        metadata=metadata,
        schema={},
        points={
            "x": np.array([1.0, 2.0, 3.0], dtype=np.float32),
            "y": np.array([0.1, 0.2, 0.3], dtype=np.float32),
            "z": np.array([0.5, 0.5, 0.5], dtype=np.float32),
            "intensity": np.array([0.8, 0.9, 1.0], dtype=np.float32),
        },
        point_count=3,
    )


# --------------------------------------------------------------------------- #
# テストケース                                                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_server_starts_and_stops():
    """start/stop が例外なく完了する。"""
    transport = WebSocketTransport(host="127.0.0.1", port=19001)
    await transport.start()
    assert transport._server is not None
    await transport.stop()
    assert transport._server is None


@pytest.mark.asyncio
async def test_client_receives_frame():
    """send したフレームをクライアントが受信できる。"""
    transport = WebSocketTransport(host="127.0.0.1", port=19002)
    await transport.start()

    received: list[dict] = []

    async def client():
        async with websockets.connect("ws://127.0.0.1:19002") as ws:
            # サーバーが send するまで少し待つ
            data = await asyncio.wait_for(ws.recv(), timeout=3.0)
            received.append(json.loads(data))

    frame = _make_frame(frame_id=42)

    # クライアントを並走させ、接続後に send する
    client_task = asyncio.create_task(client())
    await asyncio.sleep(0.05)  # クライアント接続を待つ
    await transport.send(frame)
    await client_task

    await transport.stop()

    assert len(received) == 1
    msg = received[0]
    assert msg["frame_id"] == 42
    assert "points" in msg
    assert "x" in msg["points"]
    assert len(msg["points"]["x"]) == 3
    assert abs(msg["points"]["x"][0] - 1.0) < 1e-4


@pytest.mark.asyncio
async def test_multiple_clients_receive():
    """複数クライアントが同じフレームを受信する。"""
    transport = WebSocketTransport(host="127.0.0.1", port=19003)
    await transport.start()

    received = []

    async def client():
        async with websockets.connect("ws://127.0.0.1:19003") as ws:
            data = await asyncio.wait_for(ws.recv(), timeout=3.0)
            received.append(json.loads(data))

    tasks = [asyncio.create_task(client()) for _ in range(3)]
    await asyncio.sleep(0.05)
    await transport.send(_make_frame())
    await asyncio.gather(*tasks)

    await transport.stop()
    assert len(received) == 3


@pytest.mark.asyncio
async def test_send_without_clients_does_not_raise():
    """クライアントがいない状態で send しても例外なし。"""
    transport = WebSocketTransport(host="127.0.0.1", port=19004)
    await transport.start()
    await transport.send(_make_frame())  # 例外なし
    await transport.stop()


@pytest.mark.asyncio
async def test_frame_to_json_structure():
    """_frame_to_json が正しい JSON 構造を生成する。"""
    frame = _make_frame(frame_id=7)
    payload = json.loads(WebSocketTransport._frame_to_json(frame))
    assert payload["frame_id"] == 7
    assert "timestamp" in payload
    assert isinstance(payload["timestamp"], float)
    assert set(payload["points"].keys()) >= {"x", "y", "z", "intensity"}


@pytest.mark.asyncio
async def test_client_count():
    """client_count が接続数を正しく返す。"""
    transport = WebSocketTransport(host="127.0.0.1", port=19005)
    await transport.start()
    assert transport.client_count == 0

    async with websockets.connect("ws://127.0.0.1:19005"):
        await asyncio.sleep(0.05)
        assert transport.client_count == 1

    await asyncio.sleep(0.05)
    assert transport.client_count == 0
    await transport.stop()
