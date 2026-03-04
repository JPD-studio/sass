# cepf_sdk/airy/__init__.py
"""後方互換ラッパー — 新規コードでは cepf_sdk.parsers / cepf_sdk.usc を使用してください。"""
import warnings

warnings.warn(
    "cepf_sdk.airy is deprecated. Use cepf_sdk.parsers and cepf_sdk.usc instead.",
    DeprecationWarning,
    stacklevel=2,
)

from cepf_sdk.airy.decoder import UdpAiryDecoder, AiryDecodeConfig

__all__ = ["UdpAiryDecoder", "AiryDecodeConfig"]
