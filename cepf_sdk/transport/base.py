# cepf_sdk/transport/base.py
"""TransportBase — データ転送層の抽象基底クラス"""
from __future__ import annotations

from abc import ABC, abstractmethod

from cepf_sdk.frame import CepfFrame


class TransportBase(ABC):
    """CepfFrame を外部に送信するトランスポート層の基底クラス。"""

    @abstractmethod
    async def send(self, frame: CepfFrame) -> None:
        """フレームを送信する。"""
        ...

    @abstractmethod
    async def start(self) -> None:
        """サーバー／接続を開始する。"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """サーバー／接続を停止する。"""
        ...
