"""Определение казахского текста (кириллица).

Русский текст не содержит букв Ә Ғ Қ Ң Ө Ұ Ү Һ (і — тоже казахская/украинская),
поэтому их доля среди кириллических букв — надёжный признак.
"""
from __future__ import annotations

import re

KK_SPECIFIC = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
CYR = re.compile(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
# частотные казахские слова — ловят строки, где нет специфических букв
KK_WORDS = {"мен", "сен", "ол", "біз", "сіз", "емес", "бар", "жоқ", "үшін", "және",
            "деп", "боп", "едім", "едің", "жан", "көз", "жүрек", "сүйем", "махаббат",
            "ай", "ана", "дос", "жар", "қалқам", "ғашық"}


def kazakh_stats(text: str) -> dict:
    letters = CYR.findall(text)
    total_alpha = sum(ch.isalpha() for ch in text) or 1
    kk = sum(ch in KK_SPECIFIC for ch in letters)
    lines = [l for l in text.splitlines() if CYR.search(l)]
    kk_lines = sum(any(ch in KK_SPECIFIC for ch in l) for l in lines)
    return {
        "cyr_share": len(letters) / total_alpha,
        "kk_letter_share": kk / (len(letters) or 1),
        "kk_line_share": kk_lines / (len(lines) or 1),
    }


def is_kazakh(text: str, min_line_share: float = 0.4, min_letter_share: float = 0.015,
              min_cyr_share: float = 0.8) -> bool:
    """True, если текст в основном на казахском (кириллицей).

    Русские песни и страницы с русским переводом отсекаются:
    у них мало строк со специфическими казахскими буквами.
    """
    s = kazakh_stats(text)
    return (s["cyr_share"] >= min_cyr_share
            and s["kk_letter_share"] >= min_letter_share
            and s["kk_line_share"] >= min_line_share)


def drop_non_kazakh_lines(text: str) -> str:
    """Убирает строки-переводы на русском внутри казахской страницы (по строке-блоку)."""
    out = []
    for block in re.split(r"\n\s*\n", text):
        if not block.strip() or is_kazakh(block, 0.3, 0.01, 0.7):
            out.append(block)
    return "\n\n".join(out)
