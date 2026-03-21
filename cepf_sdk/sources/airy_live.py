# cepf_sdk/sources/airy_live.py
"""UDP パケットを受信し、agg_seconds秒分を蓄積"""
from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from dataclasses import replace
from typing import Dict, Iterator, List

import numpy as np

from cepf_sdk.frame import CepfFrame
from cepf_sdk.usc import UnifiedSenseCloud

logger = logging.getLogger(__name__)


class AiryLiveSource:
    def __init__(
        self,
        usc: UnifiedSenseCloud,
        sensor_id: str,
        port: int = 6699,
        agg_seconds: float = 1.0,
        host: str = "0.0.0.0",
        socket_timeout: float = 1.0,
        recv_workers: int = 4,
        recv_queue_size: int = 2000,
    ) -> None:
        self._usc = usc
        self._sensor_id = sensor_id
        self._port = port
        self._agg_seconds = agg_seconds
        self._host = host
        self._socket_timeout = socket_timeout
        self._recv_workers = recv_workers
        self._recv_queue_size = recv_queue_size

    def frames(self) -> Iterator[CepfFrame]:
        pkt_queue: queue.Queue[bytes] = queue.Queue(maxsize=self._recv_queue_size)
        frame_queue: queue.Queue[CepfFrame] = queue.Queue(maxsize=self._recv_queue_size)
        self._stop = False

        # ── 受信スレッド ──────────────────────────────────────────────────────
        def _recv_loop() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 26214400)
            actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            logger.info("UDP SO_RCVBUF = %d bytes", actual)
            sock.bind((self._host, self._port))
            sock.settimeout(self._socket_timeout)
            logger.info(
                "AiryLiveSource: listening on %s:%d (agg=%.3fs sensor=%s)",
                self._host, self._port, self._agg_seconds, self._sensor_id,
            )
            dropped = 0
            while not self._stop:
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    pkt_queue.put_nowait(data)
                except queue.Full:
                    dropped += 1
                    if dropped % 1000 == 0:
                        logger.warning("pkt_queue full: %d dropped", dropped)
            sock.close()
            logger.info("AiryLiveSource: socket closed")

        def _forge_worker() -> None:
            while not self._stop:
                try:
                    data = pkt_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    frame = self._usc.forge(self._sensor_id, data)
                    if frame.point_count > 0:
                        frame_queue.put(frame)
                except Exception as e:
                    logger.warning("forge skipped: %s", e)

        threading.Thread(target=_recv_loop, daemon=True).start()
        for _ in range(self._recv_workers):
            threading.Thread(target=_forge_worker, daemon=True).start()
        logger.info("AiryLiveSource: %d forge workers started", self._recv_workers)

        buf: List[CepfFrame] = []
        t0 = time.time()
        try:
            while True:
                try:
                    frame = frame_queue.get(timeout=self._socket_timeout)
                except queue.Empty:
                    continue

                buf.append(frame)

                now = time.time()
                if (now - t0) < self._agg_seconds:
                    continue

                t0 = now
                if not buf:
                    continue

                merged = self._merge(buf)
                logger.info(
                    "AiryLiveSource: merged %d frames → %d points "
                    "(pkt_q=%d forge_q=%d)",
                    len(buf), merged.point_count,
                    pkt_queue.qsize(), frame_queue.qsize(),
                )
                buf = []
                yield merged
        finally:
            self._stop = True
            logger.info("AiryLiveSource: stopped")

    @staticmethod
    def _merge(frames: List[CepfFrame]) -> CepfFrame:
        """複数の部分フレームを 1 つの CepfFrame に結合する。"""
        if len(frames) == 1:
            return frames[0]

        all_keys = list(frames[0].points.keys())
        merged_points: Dict[str, np.ndarray] = {
            k: np.concatenate([np.asarray(f.points[k]) for f in frames if k in f.points])
            for k in all_keys
        }
        total = sum(f.point_count for f in frames)

        merged_ext: Dict = {}
        for f in frames:
            if not f.extensions:
                continue
            for ext_key, ext_val in f.extensions.items():
                if not isinstance(ext_val, dict):
                    merged_ext[ext_key] = ext_val
                    continue
                if ext_key not in merged_ext:
                    merged_ext[ext_key] = {}
                for field_key, field_val in ext_val.items():
                    if isinstance(field_val, np.ndarray):
                        prev = merged_ext[ext_key].get(field_key)
                        merged_ext[ext_key][field_key] = (
                            field_val if prev is None
                            else np.concatenate([prev, field_val])
                        )
                    else:
                        merged_ext[ext_key][field_key] = field_val

        base = frames[-1]
        return replace(
            base,
            points=merged_points,
            point_count=total,
            extensions=merged_ext or None,
        )
