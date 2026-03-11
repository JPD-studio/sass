# cepf_sdk/sources/airy_live.py
"""UDP パケットを受信し、0.1秒分を蓄積"""
from __future__ import annotations

import logging
import socket
import time
from dataclasses import replace
from typing import Dict, Iterator, List

import numpy as np

from cepf_sdk.frame import CepfFrame
from cepf_sdk.usc import UnifiedSenseCloud

logger = logging.getLogger(__name__)


class AiryLiveSource:
    """
    Airy の UDP パケットを受信し、agg_seconds 秒分を蓄積
    1 スキャン分の CepfFrame を 呼び出し元に値を渡して、一時停止する。
    """

    def __init__(
        self,
        usc: UnifiedSenseCloud,
        sensor_id: str,
        port: int = 6699,
        agg_seconds: float = 0.1,
        host: str = "0.0.0.0",
        socket_timeout: float = 1.0,
    ) -> None:
        self._usc = usc
        self._sensor_id = sensor_id
        self._port = port
        self._agg_seconds = agg_seconds
        self._host = host
        self._socket_timeout = socket_timeout

    def frames(self) -> Iterator[CepfFrame]:
        """UDP パケットを受信し続け、蓄積済みスキャンを呼び出し元に値を渡して、一時停止。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._host, self._port))
        sock.settimeout(self._socket_timeout)
        logger.info(
            "AiryLiveSource: listening on %s:%d (agg=%.3fs sensor=%s)",
            self._host, self._port, self._agg_seconds, self._sensor_id,
        )

        buf: List[CepfFrame] = []
        t0 = time.time()

        try:
            while True:
                # パケット受信
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue

                # 1 パケットをCepfFrameに
                try:
                    frame = self._usc.forge(self._sensor_id, data)
                except Exception as e:
                    logger.warning("forge skipped: %s", e)
                    continue

                if frame.point_count > 0:
                    buf.append(frame)

                # 蓄積時間に達したら一時停止して、値を渡す。
                now = time.time()
                if (now - t0) < self._agg_seconds:
                    continue

                t0 = now

                if not buf:
                    continue

                yield self._merge(buf)
                buf = []

        finally:
            sock.close()
            logger.info("AiryLiveSource: socket closed")

    # 内部ヘルパー   
    @staticmethod
    def _merge(frames: List[CepfFrame]) -> CepfFrame:
        """複数の部分フレームを 1 つの CepfFrame に結合する。"""
        if len(frames) == 1:
            return frames[0]

        # points
        all_keys = list(frames[0].points.keys())
        merged_points: Dict[str, np.ndarray] = {
            k: np.concatenate([np.asarray(f.points[k]) for f in frames if k in f.points])
            for k in all_keys
        }
        total = sum(f.point_count for f in frames)

        # extensions
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
                        if prev is None:
                            merged_ext[ext_key][field_key] = field_val
                        else:
                            merged_ext[ext_key][field_key] = np.concatenate([prev, field_val])
                    else:
                        merged_ext[ext_key][field_key] = field_val

        # 最後のフレームのメタデータをもとに
        base = frames[-1]
        return replace(
            base,
            points=merged_points,
            point_count=total,
            extensions=merged_ext or None,
        )
