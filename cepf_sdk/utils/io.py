# cepf_sdk/utils/io.py
"""CEPF ファイル I/O ユーティリティ"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np

from cepf_sdk.frame import CepfFrame


def load_cepf_file(filepath: Union[str, Path]) -> CepfFrame:
    """
    ファイルから CepfFrame を読み込む (JSON/Binary 自動判別)

    Parameters
    ----------
    filepath : str | Path
        CEPF ファイルパス

    Returns
    -------
    CepfFrame
    """
    path = Path(filepath)
    data = path.read_bytes()

    if data[:4] == b"CEPF":
        return CepfFrame.from_binary(data)
    else:
        return CepfFrame.from_json(data.decode("utf-8"))


def save_cepf_file(
    frame: CepfFrame, filepath: Union[str, Path], binary: bool = False
) -> None:
    """
    CepfFrame をファイルに保存

    Parameters
    ----------
    frame : CepfFrame
        保存するフレーム
    filepath : str | Path
        出力ファイルパス
    binary : bool
        True の場合バイナリ形式、False の場合 JSON 形式
    """
    path = Path(filepath)
    if binary:
        path.write_bytes(frame.to_binary())
    else:
        path.write_text(frame.to_json(), encoding="utf-8")


def cepf_to_pcd(frame: CepfFrame) -> bytes:
    """
    CepfFrame → PCD 形式 (ASCII)

    Parameters
    ----------
    frame : CepfFrame

    Returns
    -------
    bytes
        PCD ファイル内容
    """
    x = np.asarray(frame.points.get("x", np.zeros(0, dtype=np.float32)))
    y = np.asarray(frame.points.get("y", np.zeros(0, dtype=np.float32)))
    z = np.asarray(frame.points.get("z", np.zeros(0, dtype=np.float32)))
    intensity = np.asarray(frame.points.get("intensity", np.zeros(len(x), dtype=np.float32)))

    n = len(x)
    lines = [
        "# .PCD v0.7 - Point Cloud Data file format",
        "VERSION 0.7",
        "FIELDS x y z intensity",
        "SIZE 4 4 4 4",
        "TYPE F F F F",
        "COUNT 1 1 1 1",
        f"WIDTH {n}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {n}",
        "DATA ascii",
    ]
    for i in range(n):
        lines.append(f"{x[i]:.6f} {y[i]:.6f} {z[i]:.6f} {intensity[i]:.6f}")

    return "\n".join(lines).encode("ascii")


def cepf_to_las(frame: CepfFrame) -> bytes:
    """
    CepfFrame → LAS 形式

    Parameters
    ----------
    frame : CepfFrame

    Returns
    -------
    bytes
        LAS ファイル内容

    Raises
    ------
    ImportError
        laspy がインストールされていない場合
    """
    try:
        import laspy
    except ImportError:
        raise ImportError(
            "laspy が必要です: pip install cepf-sdk[io]\n"
            "または: pip install laspy"
        )

    x = np.asarray(frame.points.get("x", np.zeros(0, dtype=np.float32)))
    y = np.asarray(frame.points.get("y", np.zeros(0, dtype=np.float32)))
    z = np.asarray(frame.points.get("z", np.zeros(0, dtype=np.float32)))
    intensity = np.asarray(frame.points.get("intensity", np.zeros(len(x), dtype=np.float32)))

    header = laspy.LasHeader(point_format=0, version="1.2")
    header.offsets = [np.min(x) if len(x) > 0 else 0,
                      np.min(y) if len(y) > 0 else 0,
                      np.min(z) if len(z) > 0 else 0]
    header.scales = [0.001, 0.001, 0.001]

    las = laspy.LasData(header)
    las.x = x.astype(np.float64)
    las.y = y.astype(np.float64)
    las.z = z.astype(np.float64)
    las.intensity = (intensity * 65535).astype(np.uint16)

    import io
    buf = io.BytesIO()
    las.write(buf)
    return buf.getvalue()
