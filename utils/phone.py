import re


def phone_to_10_digits(text: str) -> str | None:
    """Нормализует номер телефона РФ к формату из 10 цифр."""

    #  Удаляем ВСЁ, кроме цифр
    digits = re.sub(r"\D", "", text)

    #  Проверяем варианты
    # 10 цифр: 9991112233
    if re.fullmatch(r"\d{10}", digits):
        return digits

    # 11 цифр с 7 или 8: 79991112233 / 89991112233
    if re.fullmatch(r"[78]\d{10}", digits):
        return digits[1:]

    return None

def format_phone_ru(phone10: str) -> str:
    """
    Форматирует номер телефона из 10 цифр в вид: +7 XXX-XXX-XX-XX.
    Если после очистки цифр не 10 — возвращает исходную строку.
    """

    digits = re.sub(r"\D", "", phone10)

    if len(digits) != 10:
        return phone10

    return f"+7 {digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:]}"
