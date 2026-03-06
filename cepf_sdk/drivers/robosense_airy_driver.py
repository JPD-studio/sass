# cepf_sdk/drivers/robosense_airy_driver.py
"""
RoboSense Airy パケットデコーダー（ドライバー層）。

公式 SDK が提供されていない RoboSense Airy の生 UDP パケットを
デコードするための自前実装。Ouster における ouster-sdk と同じ役割。

責任:
  - 1248 バイトの UDP パケットをデコードし、各チャンネルの距離・角度・強度を返す
  - CepfFrame は知らない（パーサー層の仕事）
  - UDP ソケットは管理しない（apps/ 層の仕事）
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---- パケット定数（decoder.py から移植） ----
PKT_LEN = 1248       # 1 パケットのバイト数
HDR = 42             # MSOP ヘッダ長
DB_SIZE = 148        # 1 Data Block のサイズ
N_DB = 8             # 1 パケット内の Data Block 数
CH_PER_DB = 48       # 1 Data Block 内のチャンネル数（上位 + 下位）
REC_SIZE = 3         # 2 bytes distance + 1 byte reflectivity
DIST_MASK = 0x3FFF   # 14bit 距離値のマスク
FLAG_EXPECT = 0xFFEE # 有効な Data Block のフラグ値
TICK_OFF = 26        # タイムスタンプのバイトオフセット

FLAG_OFF = 0         # Data Block 先頭フラグ
AZ_OFF = 2           # 方位角オフセット
CH_OFF = 3           # チャンネルデータ開始オフセット


def _be_u16(b: bytes, off: int) -> int:
    """Big-endian 16bit unsigned"""
    return struct.unpack(">H", b[off:off + 2])[0]


def _be_u32(b: bytes, off: int) -> int:
    """Big-endian 32bit unsigned"""
    return struct.unpack(">I", b[off:off + 4])[0]


# ---- デフォルト96chの仰角テーブル ----
_DEFAULT_VERT_DEG_96 = tuple(np.linspace(-15.0, 15.0, 96).tolist())


@dataclass
class AiryPacketData:
    """1 パケット分のデコード結果。CepfFrame とは無関係。"""
    azimuth_deg: np.ndarray     # (N_points,) 各点の方位角 [deg]
    elevation_deg: np.ndarray   # (N_points,) 各点の仰角 [deg]
    distance_m: np.ndarray      # (N_points,) 距離 [m]
    intensity_raw: np.ndarray   # (N_points,) 生強度値 [0-255]
    timestamp_us: int           # パケットタイムスタンプ [μs相当の生値]
    ring: np.ndarray            # (N_points,) チャンネル番号
    dist_word_u16: np.ndarray   # (N_points,) 距離生ワード
    dist_raw_u16: np.ndarray    # (N_points,) マスク済み距離値


@dataclass
class AiryDriverConfig:
    """ドライバー設定。バイナリ解析に関する部分のみ。"""
    vert_deg: tuple = _DEFAULT_VERT_DEG_96
    dist_scale_m: float = 0.002
    intensity_div: float = 255.0


def decode_packet(pkt: bytes, config: Optional[AiryDriverConfig] = None) -> Optional[AiryPacketData]:
    """
    1248 バイトの Airy パケットをデコードする。
    decoder.py._decode_packet_cols() から移植。

    Parameters
    ----------
    pkt : bytes
        受信した生パケット（len == 1248）
    config : AiryDriverConfig | None
        デコード設定。None の場合はデフォルト

    Returns
    -------
    AiryPacketData | None
        無効なパケットの場合は None
    """
    if len(pkt) != PKT_LEN:
        return None

    if config is None:
        config = AiryDriverConfig()

    vert_deg = np.asarray(config.vert_deg, dtype=np.float32)
    n_channels = len(vert_deg)

    timestamp_raw = _be_u32(pkt, TICK_OFF)

    azs = []
    els = []
    dists = []
    intens = []
    rings = []
    dist_words = []
    dist_raws = []

    for dbi in range(N_DB):
        bs = HDR + dbi * DB_SIZE
        db = pkt[bs:bs + DB_SIZE]
        if len(db) != DB_SIZE:
            continue

        flag = _be_u16(db, FLAG_OFF)
        if flag != FLAG_EXPECT:
            continue

        az_deg = _be_u16(db, AZ_OFF) / 100.0
        ch_base = 0 if (dbi % 2 == 0) else CH_PER_DB

        for ci in range(CH_PER_DB):
            off = CH_OFF + ci * REC_SIZE
            d_word = _be_u16(db, off)
            d_raw = d_word & DIST_MASK
            if d_raw == 0:
                continue

            inten = db[off + 2]
            ring = ch_base + ci
            if ring >= n_channels:
                continue

            r = d_raw * config.dist_scale_m
            el = float(vert_deg[ring])

            azs.append(((az_deg + 180.0) % 360.0) - 180.0)
            els.append(el)
            dists.append(r)
            intens.append(inten)
            rings.append(ring)
            dist_words.append(d_word)
            dist_raws.append(d_raw)

    if not azs:
        return None

    return AiryPacketData(
        azimuth_deg=np.asarray(azs, dtype=np.float32),
        elevation_deg=np.asarray(els, dtype=np.float32),
        distance_m=np.asarray(dists, dtype=np.float32),
        intensity_raw=np.asarray(intens, dtype=np.uint8),
        timestamp_us=int(timestamp_raw),
        ring=np.asarray(rings, dtype=np.uint8),
        dist_word_u16=np.asarray(dist_words, dtype=np.uint16),
        dist_raw_u16=np.asarray(dist_raws, dtype=np.uint16),
    )


def validate_packet(pkt: bytes) -> bool:
    """パケットの基本的な妥当性を検証する。"""
    if len(pkt) != PKT_LEN:
        return False
    # 最低1つの Data Block が有効フラグを持つか
    for dbi in range(N_DB):
        bs = HDR + dbi * DB_SIZE
        if bs + 2 <= len(pkt):
            flag = _be_u16(pkt, bs + FLAG_OFF)
            if flag == FLAG_EXPECT:
                return True
    return False
