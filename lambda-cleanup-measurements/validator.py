import re
from decimal import Decimal, InvalidOperation

NUMERIC_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

class SensorValidator:
    @staticmethod
    def clean_scalar(value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip().replace("\u00a0", " ")
            if cleaned.startswith("'"):
                cleaned = cleaned[1:].strip()
            return cleaned
        return value

    @staticmethod
    def parse_decimal(value):
        value = SensorValidator.clean_scalar(value)
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str) and NUMERIC_PATTERN.fullmatch(value):
            try:
                return Decimal(value)
            except InvalidOperation:
                return None
        return None

    @staticmethod
    def parse_epoch_int(value):
        dec = SensorValidator.parse_decimal(value)
        if dec is None:
            return None
        try:
            return int(dec)
        except Exception:
            return None

    @staticmethod
    def parse_bool_int(value):
        value = SensorValidator.clean_scalar(value)
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int):
            return value if value in (0, 1) else None
        if isinstance(value, Decimal):
            iv = int(value)
            return iv if iv in (0, 1) and value == Decimal(iv) else None
        if isinstance(value, str):
            v = value.lower()
            if v in {"true", "1", "yes", "on"}:
                return 1
            if v in {"false", "0", "no", "off"}:
                return 0
        return None

    @staticmethod
    def parse_bitmask(value, num_bits):
        value = SensorValidator.clean_scalar(value)
        if isinstance(value, bool):
            return None
        iv = None
        if isinstance(value, int):
            iv = value
        elif isinstance(value, Decimal):
            if value == int(value):
                iv = int(value)
        elif isinstance(value, str) and NUMERIC_PATTERN.fullmatch(value):
            try:
                iv = int(Decimal(value))
            except InvalidOperation:
                return None
        if iv is None:
            return None
        max_value = (1 << num_bits) - 1
        return iv if 0 <= iv <= max_value else None
