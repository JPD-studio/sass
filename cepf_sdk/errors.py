# cepf_sdk/errors.py
"""CEPF SDK 例外階層"""


class CEPFError(Exception):
    """CEPF SDK 基底例外"""


class ParseError(CEPFError):
    """パース失敗"""


class InvalidHeaderError(ParseError):
    """ヘッダー不正"""


class InvalidDataError(ParseError):
    """データ不正"""


class ChecksumError(ParseError):
    """チェックサム不一致"""


class ValidationError(CEPFError):
    """バリデーション失敗"""


class ConfigurationError(CEPFError):
    """設定エラー"""


class SensorNotFoundError(ConfigurationError):
    """未登録センサー"""


class ParserNotFoundError(ConfigurationError):
    """未登録パーサー"""


class SerializationError(CEPFError):
    """シリアライズ/デシリアライズ失敗"""
