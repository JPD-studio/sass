# cepf_sdk/sources/ouster_pcap.py
"""Ouster PCAP ソース — PCAP 再生を AiryLiveSource と同一レイヤーで提供

ouster_pcap_replay.py の実績ある IP フラグメント再結合 + ouster-sdk デコードロジックを
Source インターフェース (Iterator[CepfFrame]) として再パッケージ。

データフロー:
    PCAP → IP fragment reassembly → ouster ScanBatcher → XYZLut → CepfFrame yield

使い方:
    source = OusterPcapSource(pcap_path, meta_path, rate=1.0, loop=True)
    for frame in source.frames():
        # frame は CepfFrame — FilterPipeline にそのまま渡せる
        ...
"""
from __future__ import annotations

import logging
import struct
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import numpy as np

from cepf_sdk.frame import CepfFrame, CepfMetadata

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# IP フラグメント再結合 → UDP ペイロードイテレーター                     #
#   ouster_pcap_replay.py の実績あるロジックをそのまま移植              #
# ------------------------------------------------------------------ #

def _iter_udp_payloads(pcap_path: Path,
                       lidar_port: int = 7502) -> Iterator[Tuple[float, bytes]]:
    """
    pcapng/pcap を読み込み、IP フラグメントを再結合して
    指定 UDP ポート宛の UDP ペイロード (ヘッダー除く) を yield する。
    """
    try:
        import dpkt
        import dpkt.pcapng
    except ImportError:
        logger.error("dpkt が必要: python3 -m pip install dpkt")
        sys.exit(1)

    magic = pcap_path.read_bytes()[:4]
    fh = open(pcap_path, "rb")
    reader = (dpkt.pcapng.Reader(fh) if magic == b"\x0a\x0d\x0d\x0a"
              else dpkt.pcap.Reader(fh))

    frags: Dict[tuple, list] = {}
    frag_ts: Dict[tuple, float] = {}

    try:
        for ts, buf in reader:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                if not isinstance(eth.data, dpkt.ip.IP):
                    continue
                ip = eth.data
                if ip.p != 17:  # UDP only
                    continue

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    off_raw = ip.off

                mf = bool((off_raw >> 13) & 0x1)
                frag_off = (off_raw & 0x1FFF) * 8
                key = (bytes(ip.src), bytes(ip.dst), ip.id)

                if isinstance(ip.data, dpkt.udp.UDP):
                    udp_hdr = bytes(ip.data)[:8]
                    frags.setdefault(key, []).append(
                        (frag_off, bytes(ip.data.data), True, udp_hdr))
                    frag_ts.setdefault(key, float(ts))
                else:
                    frags.setdefault(key, []).append(
                        (frag_off, bytes(ip.data), False, None))

                if not mf:
                    parts = frags.pop(key, [])
                    emit_ts = frag_ts.pop(key, float(ts))
                    parts.sort(key=lambda x: x[0])

                    udp_hdr = next((h for _, _, u, h in parts if u and h), None)
                    if udp_hdr is None:
                        continue
                    _sport, dport = struct.unpack("!HH", udp_hdr[:4])
                    if dport != lidar_port:
                        continue

                    payload = b"".join(data for _, data, _, _ in parts)
                    if payload:
                        yield emit_ts, payload
            except Exception:
                pass
    finally:
        fh.close()


# ------------------------------------------------------------------ #
# OusterPcapSource                                                      #
# ------------------------------------------------------------------ #

class OusterPcapSource:
    """
    Ouster PCAP を読み込み、CepfFrame を yield するソース。
    AiryLiveSource と同一インターフェース (frames() → Iterator[CepfFrame])。

    Args:
        pcap_path:  PCAP ファイルパス
        meta_path:  Ouster センサーメタデータ JSON パス
        rate:       再生速度倍率 (1.0=実時間, 0=最速)
        loop:       True ならループ再生
        lidar_port: UDP ポート (デフォルト: 7502)
    """

    def __init__(
        self,
        pcap_path: Path | str,
        meta_path: Path | str,
        rate: float = 1.0,
        loop: bool = True,
        lidar_port: int = 7502,
        flip_z: bool = False,
    ) -> None:
        self._pcap_path = Path(pcap_path)
        self._meta_path = Path(meta_path)
        self._rate = rate
        self._loop = loop
        self._lidar_port = lidar_port
        self._flip_z = flip_z

        if not self._pcap_path.exists():
            raise FileNotFoundError(f"PCAP not found: {self._pcap_path}")
        if not self._meta_path.exists():
            raise FileNotFoundError(f"Meta JSON not found: {self._meta_path}")

    def frames(self) -> Iterator[CepfFrame]:
        """PCAP を読み込み、フレームごとに CepfFrame を yield する。"""
        pass_num = 0
        while True:
            pass_num += 1
            logger.info("OusterPcapSource: パス %d 開始 (%s)", pass_num, self._pcap_path.name)
            yield from self._single_pass(pass_num)

            if not self._loop:
                break
            logger.info("OusterPcapSource: ループ再生 — 2秒後にパス %d 開始", pass_num + 1)
            time.sleep(2.0)

        logger.info("OusterPcapSource: 再生完了 (計 %d パス)", pass_num)

    def _single_pass(self, pass_num: int) -> Iterator[CepfFrame]:
        """1パス分の PCAP フレームを yield する。"""
        try:
            from ouster.sdk.core import SensorInfo, XYZLut, ChanField
            from ouster.sdk._bindings.client import (
                PacketFormat as PF,
                LidarPacket,
                ScanBatcher,
                LidarScan,
            )
        except ImportError:
            logger.error("ouster-sdk が必要: pip install ouster-sdk")
            sys.exit(1)

        with open(self._meta_path) as f:
            info = SensorInfo(f.read())
        pf = PF(info)
        xyz_lut = XYZLut(info)
        pkt_sz = pf.lidar_packet_size

        logger.info("OusterPcapSource: lidar_packet_size=%d, profile=%s, flip_z=%s",
                     pkt_sz, info.format.udp_profile_lidar, self._flip_z)

        batcher = ScanBatcher(info)
        scan = LidarScan(info)

        frame_id = 0
        first_ts = None
        start_mono = time.monotonic()

        for ts, payload in _iter_udp_payloads(self._pcap_path, self._lidar_port):
            if len(payload) != pkt_sz:
                continue

            pkt = LidarPacket(pkt_sz)
            pkt.buf[:] = np.frombuffer(payload, dtype=np.uint8)

            if first_ts is None:
                first_ts = ts

            if batcher(pkt, scan):
                # フレーム完成 → XYZ 変換
                xyz = xyz_lut(scan).reshape(-1, 3).astype(np.float32)
                rng = scan.field(ChanField.RANGE).reshape(-1)
                valid = rng > 0
                pts = xyz[valid]

                if len(pts) == 0:
                    frame_id += 1
                    continue

                # Z軸反転 (物理的に下向き設置されたセンサー用)
                if self._flip_z:
                    pts[:, 2] = -pts[:, 2]

                # レート制御
                if self._rate > 0 and frame_id > 0 and first_ts is not None:
                    wait = (ts - first_ts) / self._rate - (time.monotonic() - start_mono)
                    if wait > 0:
                        time.sleep(wait)

                # CepfFrame を構築
                frame = self._make_frame(pts, frame_id, ts)

                if frame_id % 20 == 0:
                    logger.info("OusterPcapSource: pass=%d frame=%d points=%d",
                               pass_num, frame_id, len(pts))

                yield frame
                frame_id += 1

        logger.info("OusterPcapSource: パス %d 完了 (%d フレーム)", pass_num, frame_id)

    @staticmethod
    def _make_frame(pts: np.ndarray, frame_id: int, pcap_ts: float) -> CepfFrame:
        """numpy XYZ 配列を CepfFrame にラップする。"""
        metadata = CepfMetadata(
            timestamp_utc=datetime.fromtimestamp(pcap_ts, tz=timezone.utc).isoformat(),
            frame_id=frame_id,
            coordinate_system="sensor_local",
            coordinate_mode="cartesian",
            units={"distance": "m"},
            sensor={"model": "Ouster OS-1", "source": "pcap_replay"},
        )
        points: Dict[str, np.ndarray] = {
            "x": pts[:, 0],
            "y": pts[:, 1],
            "z": pts[:, 2],
        }
        return CepfFrame(
            format="CEPF",
            version="1.4.0",
            metadata=metadata,
            schema={"fields": ["x", "y", "z"],
                    "types": ["float32", "float32", "float32"]},
            points=points,
            point_count=len(pts),
            extensions=None,
        )
