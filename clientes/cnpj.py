import re

from django.core.exceptions import ValidationError

CNPJ_DIGITS_RE = re.compile(r"\D+")


def only_digits(value: str) -> str:
    return CNPJ_DIGITS_RE.sub("", value or "")


def format_cnpj(value: str) -> str:
    digits = only_digits(value)
    if len(digits) != 14:
        return value or ""
    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def _check_digit(digits: str, weights: list[int]) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(digits, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False

    first = _check_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    if first != int(digits[12]):
        return False

    second = _check_digit(digits[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return second == int(digits[13])


def validate_cnpj(value: str) -> str:
    digits = only_digits(value)
    if len(digits) != 14:
        raise ValidationError("Informe um CNPJ com 14 dígitos.")
    if not is_valid_cnpj(digits):
        raise ValidationError("CNPJ inválido.")
    return format_cnpj(digits)
