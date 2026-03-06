# tests/test_transport/test_base.py
"""TransportBase 抽象クラスのテスト"""
import pytest
from cepf_sdk.transport.base import TransportBase


def test_cannot_instantiate_transport_base():
    """TransportBase は抽象クラスなのでインスタンス化できない。"""
    with pytest.raises(TypeError):
        TransportBase()  # type: ignore


def test_concrete_subclass_must_implement_all_methods():
    """send/start/stop のいずれかを実装しないと TypeError。"""
    class Partial(TransportBase):
        async def start(self): pass
        async def stop(self): pass
        # send は未実装

    with pytest.raises(TypeError):
        Partial()


def test_concrete_subclass_is_instantiable():
    """全メソッドを実装すればインスタンス化できる。"""
    class Concrete(TransportBase):
        async def send(self, frame): pass
        async def start(self): pass
        async def stop(self): pass

    obj = Concrete()
    assert obj is not None
