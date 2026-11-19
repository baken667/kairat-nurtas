"""Парсер песен исполнителя через Genius API + разбор HTML страниц текстов.

Использование:
    export GENIUS_TOKEN=...   # https://genius.com/api-clients
    python -m kairat.parser --artist "Kairat Nurtas" --out data/songs.jsonl

Выход: JSONL, одна песня на строку (сырые данные; чистка — в decoder.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Iterator

import requests
from bs4 import BeautifulSoup

API = "https://api.genius.com"
UA = "Mozilla/5.0 (compatible; lyrics-dataset-builder/1.0)"


# ---------- разбор HTML (чистая функция, тестируется без сети) ----------
def parse_lyrics_html(html: str) -> str:
    """Достаёт текст песни из HTML страницы Genius."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select('div[data-lyrics-container="true"]')
    if not containers:  # старая вёрстка
        old = soup.select_one("div.lyrics")
        containers = [old] if old else []
    parts = []
    for c in containers:
        # убираем шапку/блоки «Contributors», «Embed» и т.п.
        for junk in c.select('[data-exclude-from-selection="true"]'):
            junk.decompose()
        for br in c.find_all("br"):
            br.replace_with("\n")
        parts.append(c.get_text())
    return "\n".join(p.strip("\n") for p in parts).strip()


# ---------- сеть ----------
class Genius:
    def __init__(self, token: str, delay: float = 1.0):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.token, self.delay = token, delay

    def _get(self, url: str, **kw) -> requests.Response:
        for attempt in range(4):
            r = self.s.get(url, timeout=30, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
            time.sleep(self.delay)  # вежливая задержка
            return r
        r.raise_for_status()
        return r

    def api(self, path: str, **params) -> dict:
        r = self._get(API + path, params=params,
                      headers={"Authorization": f"Bearer {self.token}"})
        return r.json()["response"]

    def find_artist_id(self, name: str) -> int:
        norm = lambda s: re.sub(r"\W+", "", s.casefold())
        for hit in self.api("/search", q=name)["hits"]:
            a = hit["result"]["primary_artist"]
            if norm(a["name"]) == norm(name):
                return a["id"]
        raise SystemExit(f"Артист «{name}» не найден. Попробуйте другое написание "
                         "(например, «Kairat Nurtas» / «Қайрат Нұртас» / «Кайрат Нуртас»).")

    def artist_songs(self, artist_id: int) -> Iterator[dict]:
        page = 1
        while page:
            resp = self.api(f"/artists/{artist_id}/songs", per_page=50, page=page, sort="popularity")
            for song in resp["songs"]:
                if song["primary_artist"]["id"] == artist_id:  # только свои, без фитов-чужих
                    yield song
            page = resp.get("next_page")

    def song_details(self, song_id: int) -> dict:
        return self.api(f"/songs/{song_id}", text_format="plain")["song"]

    def lyrics(self, url: str) -> str:
        return parse_lyrics_html(self._get(url).text)


def build_record(song: dict, lyrics: str) -> dict:
    album = song.get("album") or {}
    return {
        "id": song["id"],
        "title": song.get("title"),
        "artist": song["primary_artist"]["name"],
        "album": album.get("name"),
        "release_date": song.get("release_date"),
        "url": song.get("url"),
        "language": song.get("language"),
        "lyrics": lyrics,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--artist", default="Kairat Nurtas")
    ap.add_argument("--out", default="data/songs.jsonl")
    ap.add_argument("--token", default=os.environ.get("GENIUS_TOKEN"))
    ap.add_argument("--delay", type=float, default=1.0, help="пауза между запросами, сек")
    ap.add_argument("--limit", type=int, default=0, help="0 = без ограничения")
    a = ap.parse_args(argv)
    if not a.token:
        ap.error("нужен токен Genius: --token или переменная GENIUS_TOKEN")

    g = Genius(a.token, a.delay)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    seen = set()  # возобновление: пропускаем уже скачанное
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            seen = {json.loads(l)["id"] for l in f if l.strip()}

    aid = g.find_artist_id(a.artist)
    n = 0
    with open(a.out, "a", encoding="utf-8") as out:
        for s in g.artist_songs(aid):
            if s["id"] in seen:
                continue
            try:
                text = g.lyrics(s["url"])
                if not text:
                    print(f"[пусто] {s['title']}", file=sys.stderr)
                    continue
                rec = build_record(g.song_details(s["id"]), text)
            except requests.RequestException as e:
                print(f"[ошибка] {s['title']}: {e}", file=sys.stderr)
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            print(f"[{n}] {rec['title']}", file=sys.stderr)
            if a.limit and n >= a.limit:
                break
    print(f"Готово: +{n} песен → {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
