#!/usr/bin/env python3
"""
demo_pcap_generator.py
Velodyne VLP-16 フォーマットのダミー PCAP ファイルを生成する。

使い方:
    python3 apps/generate_demo_pcap.py --output demo.pcap --frames 10
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

try:
    import dpkt
except ImportError:
    print("Error: dpkt が必要です。実行: python3 -m pip install dpkt")
    sys.exit(1)


def generate_velodyne_packet(frame_id: int, num_blocks: int = 12) -> bytes:
    """
    簡素化された Velodyne VLP-16 パケット（UDP ペイロード）を生成。
    実際の Velodyne パケット構造に準拠（PACKET_SIZE = 1206 bytes）。
    """
    packet = bytearray(1206)
    
    # 12 blocks × 100 bytes/block
    for block_idx in range(num_blocks):
        offset = block_idx * 100
        
        # ブロックヘッダー
        packet[offset:offset+2] = struct.pack("<H", 0xFFEE)           # block flag
        packet[offset+2:offset+4] = struct.pack("<H", frame_id * 10)  # azimuth
        
        # 32 チャネル（各 3 bytes: 距離 2 + 反射強度 1）
        for ch in range(32):
            offset_ch = offset + 4 + ch * 3
            
            # 距離（0～100m、スケール 2mm）
            distance_mm = int((10 + frame_id * 0.5 + ch * 0.1) * 500) & 0xFFFF
            packet[offset_ch:offset_ch+2] = struct.pack("<H", distance_mm)
            
            # 反射強度（0～255）
            intensity = (128 + frame_id * 5 + ch * 2) & 0xFF
            packet[offset_ch+2] = intensity
    
    # タイムスタンプ（最後 4 bytes）
    timestamp = 1234567890 + frame_id
    packet[1200:1206] = struct.pack("<I", timestamp) + b"\xf0\x11"
    
    return bytes(packet)


def create_pcap(output_path: Path, num_frames: int = 10) -> None:
    """PCAP ファイルを生成する。"""
    with open(output_path, "wb") as f:
        # PCAP グローバルヘッダー
        pcap_header = struct.pack(
            "<IHHIIII",
            0xa1b2c3d4,  # magic number
            2, 4,        # version
            0, 0,        # thiszone, sigfigs
            65535, 1     # snaplen, network (Ethernet)
        )
        f.write(pcap_header)
        
        # パケットレコード
        for frame_id in range(num_frames):
            # UDP/IP/Ethernet フレーム構築（簡素版）
            velodyne_payload = generate_velodyne_packet(frame_id)
            
            # Ethernet ヘッダー (14 bytes)
            eth = bytes.fromhex("ffffffffffff") + bytes.fromhex("aabbccddee00") + b"\x08\x00"
            
            # IP ヘッダー (20 bytes) — 簡素化
            ip_header = bytearray(20)
            ip_header[0] = 0x45                    # version + IHL
            ip_header[2:4] = struct.pack(">H", 20 + 8 + len(velodyne_payload))  # total length
            ip_header[6:8] = struct.pack(">H", 0)  # flags + fragment offset
            ip_header[9] = 17                      # protocol (UDP)
            ip_header[12:16] = bytes([192, 168, 1, 100])  # src IP
            ip_header[16:20] = bytes([192, 168, 1, 200])  # dst IP
            
            # UDP ヘッダー (8 bytes)
            udp_header = struct.pack(
                ">HHHH",
                2368,                              # src port
                2369,                              # dst port (Velodyne Lidar)
                8 + len(velodyne_payload),        # length
                0                                  # checksum (0 = disabled)
            )
            
            frame = eth + bytes(ip_header) + udp_header + velodyne_payload
            
            # PCAP パケットレコードヘッダー
            ts_sec = 1234567890 + frame_id
            ts_usec = (frame_id % 1000) * 1000
            record_header = struct.pack(
                "<IIII",
                ts_sec, ts_usec,
                len(frame),   # incl_len
                len(frame)    # orig_len
            )
            
            f.write(record_header)
            f.write(frame)


def main() -> None:
    p = argparse.ArgumentParser(description="Velodyne VLP-16 デモ PCAP ファイルを生成")
    p.add_argument(
        "--output", "-o",
        default="demo.pcap",
        help="出力ファイルパス (default: demo.pcap)",
    )
    p.add_argument(
        "--frames",
        type=int,
        default=10,
        help="生成するフレーム数 (default: 10)",
    )
    args = p.parse_args()
    
    output_path = Path(args.output)
    try:
        create_pcap(output_path, args.frames)
        print(f"✓ デモ PCAP を生成しました: {output_path}")
        print(f"  フレーム数: {args.frames}")
        print(f"  ファイルサイズ: {output_path.stat().st_size} bytes")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
