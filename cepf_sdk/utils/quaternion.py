# cepf_sdk/utils/quaternion.py
"""クォータニオン⇔回転行列変換"""
from __future__ import annotations

import numpy as np


def quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """
    クォータニオン [w, x, y, z] → 3x3 回転行列

    Parameters
    ----------
    q : ndarray, shape (4,)
        正規化済みクォータニオン [w, x, y, z]

    Returns
    -------
    ndarray, shape (3, 3)
        回転行列
    """
    q = np.asarray(q, dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.eye(3, dtype=np.float64)
    q = q / norm

    w, x, y, z = q

    R = np.array([
        [1 - 2*(y*y + z*z),  2*(x*y - w*z),      2*(x*z + w*y)],
        [2*(x*y + w*z),      1 - 2*(x*x + z*z),  2*(y*z - w*x)],
        [2*(x*z - w*y),      2*(y*z + w*x),      1 - 2*(x*x + y*y)],
    ], dtype=np.float64)

    return R


def rotation_matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """
    3x3 回転行列 → クォータニオン [w, x, y, z]

    Parameters
    ----------
    R : ndarray, shape (3, 3)
        回転行列

    Returns
    -------
    ndarray, shape (4,)
        正規化済みクォータニオン [w, x, y, z]
    """
    R = np.asarray(R, dtype=np.float64)
    trace = np.trace(R)

    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    q = np.array([w, x, y, z], dtype=np.float64)
    q /= np.linalg.norm(q)
    return q
