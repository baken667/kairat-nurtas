"""Декодер: сырой JSONL (parser.py) → чистые датасеты для обучения.

Форматы (--format):
    text   {"text": "..."}                                  — для continued pretraining
    chat   {"messages": [user, assistant]}                  — для SFT (chat)
    alpaca {"instruction","input","output"}                 — для SFT (alpaca)
    raw    очищенная запись со всеми метаданными

Примеры:
    python -m kairat.decoder data/songs.jsonl data/train.jsonl --format chat
    python -m kairat.decoder data/songs.jsonl data/text.jsonl --format text --keep-tags
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from typing import Iterable, Iterator

from .kazakh import is_kazakh

SECTION_RE = re.compile(r"^\s*\[[^\]]*\]\s*$")          # [Куплет 1], [Chorus] ...
MOJIBAKE_RE = re.compile(r"[ÐÑÃ][\x80-\xbf]")           # «Ð\x9aÐ°...» — UTF-8, прочитанный как latin-1


def fix_encoding(s: str) -> str:
    """Чинит «кракозябры» (UTF-8 → latin-1/cp1252) и HTML-сущности."""
    if MOJIBAKE_RE.search(s):
        for enc in ("latin-1", "cp1252"):
            try:
                s = s.encode(enc).decode("utf-8")
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return html.unescape(s)


def clean_lyrics(text: str, keep_tags: bool = False) -> str:
    text = fix_encoding(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("​", "").replace("﻿", "").replace("\xa0", " ")
    text = re.sub(r"\d*Embed$", "", text.strip())                      # хвост «123Embed»
    text = re.sub(r"^.*?Lyrics\s*\n", "", text, count=1) if re.match(r"^[^\n]{0,120}Lyrics\s*\n", text) else text
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        if not keep_tags and SECTION_RE.match(ln):
            ln = ""
        lines.append(ln)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_jsonl(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[пропуск] строка {i}: {e}", file=sys.stderr)


def convert(rec: dict, fmt: str, keep_tags: bool) -> dict:
    lyr = clean_lyrics(rec["lyrics"], keep_tags)
    title, artist = fix_encoding(rec.get("title") or ""), fix_encoding(rec.get("artist") or "")
    if fmt == "text":
        return {"text": lyr}
    if fmt == "chat":
        return {"messages": [
            {"role": "user", "content": f"Напиши текст песни «{title}» в стиле {artist}."},
            {"role": "assistant", "content": lyr},
        ]}
    if fmt == "alpaca":
        return {"instruction": f"Напиши текст песни «{title}» в стиле {artist}.",
                "input": "", "output": lyr}
    return {**rec, "title": title, "artist": artist, "lyrics": lyr}


def decode(records: Iterable[dict], fmt="chat", keep_tags=False, min_chars=50,
           kazakh_only=True) -> Iterator[dict]:
    seen = set()
    for rec in records:
        if not rec.get("lyrics"):
            continue
        out = convert(rec, fmt, keep_tags)
        body = clean_lyrics(rec["lyrics"], keep_tags)
        if len(body) < min_chars:
            continue
        if kazakh_only and not is_kazakh(body):
            continue
        h = hashlib.sha1(re.sub(r"\W+", "", body.casefold()).encode()).hexdigest()
        if h in seen:                       # дубликаты (ремиксы, перепосты)
            continue
        seen.add(h)
        yield out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--format", choices=["text", "chat", "alpaca", "raw"], default="chat")
    ap.add_argument("--keep-tags", action="store_true", help="оставить [Куплет]/[Припев]")
    ap.add_argument("--min-chars", type=int, default=50)
    ap.add_argument("--any-language", action="store_true", help="не отбрасывать не-казахские тексты")
    a = ap.parse_args(argv)
    n = 0
    with open(a.dst, "w", encoding="utf-8") as out:
        for item in decode(read_jsonl(a.src), a.format, a.keep_tags, a.min_chars, not a.any_language):
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            n += 1
    print(f"Записано {n} примеров → {a.dst}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
