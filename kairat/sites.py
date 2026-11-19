"""Универсальный парсер казахстанских сайтов с текстами песен (по конфигу).

    python -m kairat.sites --config sources.json --out data/songs.jsonl

sources.json — список сайтов; селекторы подбираются под вёрстку (DevTools → Copy selector):
[
  {
    "name": "example-site",
    "start_urls": ["https://example.kz/artist/kairat-nurtas"],   # страницы со списком песен
    "link_selector": "a.song-link",                              # ссылки на песни
    "title_selector": "h1",
    "lyrics_selector": "div.lyrics",
    "artist_selector": null,                                     # опц.; иначе берётся artist из конфига
    "line_selector": null,                                       # опц.: селектор строки внутри lyrics_selector
    "link_filter": null,                                         # опц.: regex по тексту ссылки (фильтр по исполнителю)
    "title_split": null,                                         # опц.: напр. " - " для заголовков «Исполнитель - Песня»
    "max_songs": 0,                                              # опц.: лимит (0 = все)
    "artist": "Қайрат Нұртас",
    "next_selector": "a.next",                                   # опц., пагинация
    "max_pages": 20
  }
]
Для matinder.kz готовый конфиг — sources.json.
Отбираются ТОЛЬКО песни на казахском (kairat.kazakh.is_kazakh). Учитывается robots.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.robotparser
from typing import Callable, Iterator
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .kazakh import drop_non_kazakh_lines, is_kazakh

UA = "Mozilla/5.0 (compatible; lyrics-dataset-builder/1.0)"


def extract_text(node, line_selector: str | None = None) -> str:
    if line_selector:  # каждая строка песни — отдельный элемент, пустой элемент = конец куплета
        lines = [" ".join(el.get_text().split()) for el in node.select(line_selector)]
        return "\n".join(lines).strip().replace("\n\n\n", "\n\n")
    for br in node.find_all("br"):
        br.replace_with("\n")
    for p in node.find_all(["p", "div"]):
        p.append("\n")
    lines = [l.strip() for l in node.get_text().splitlines()]
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def parse_song_page(html: str, cfg: dict, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(cfg["lyrics_selector"])
    if not node:
        return None
    title_node = soup.select_one(cfg.get("title_selector", "h1"))
    artist_node = soup.select_one(cfg["artist_selector"]) if cfg.get("artist_selector") else None
    lyrics = drop_non_kazakh_lines(extract_text(node, cfg.get("line_selector")))
    title = None
    if title_node:
        for small in title_node.find_all("small"):
            small.decompose()
        title = title_node.get_text(" ", strip=True)
    artist = artist_node.get_text(strip=True) if artist_node else cfg.get("artist")
    if title and cfg.get("title_split") and cfg["title_split"] in title:
        artist, title = (x.strip() for x in title.split(cfg["title_split"], 1))
    return {
        "id": "site:" + hashlib.sha1(url.encode()).hexdigest()[:16],
        "title": title,
        "artist": artist,
        "album": None, "release_date": None, "url": url,
        "language": "kk", "source": cfg["name"], "lyrics": lyrics,
    }


def song_links(html: str, cfg: dict, base: str) -> tuple[list[str], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    flt = re.compile(cfg["link_filter"], re.I) if cfg.get("link_filter") else None
    links = [urljoin(base, a["href"]) for a in soup.select(cfg["link_selector"])
             if a.get("href") and (not flt or flt.search(a.get_text(" ", strip=True)))]
    nxt = soup.select_one(cfg["next_selector"]) if cfg.get("next_selector") else None
    return links, (urljoin(base, nxt["href"]) if nxt and nxt.get("href") else None)


class Fetcher:
    def __init__(self, delay: float = 1.5):
        self.s, self.delay, self._robots = requests.Session(), delay, {}
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "kk,ru;q=0.5"})

    def allowed(self, url: str) -> bool:
        host = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:  # качаем тем же клиентом/UA: urllib по умолчанию часто получает 403 и считает это полным запретом
                r = self.s.get(host + "/robots.txt", timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:  # нет robots.txt (404 и т.п.) → ограничений нет
                    rp = None
            except requests.RequestException:
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        return rp is None or rp.can_fetch(UA, url)

    def get(self, url: str) -> str | None:
        if not self.allowed(url):
            print(f"[robots.txt запрещает] {url}", file=sys.stderr)
            return None
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=30)
                if r.status_code in (429, 503):
                    time.sleep(2 ** attempt * 3)
                    continue
                r.raise_for_status()
                r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
                time.sleep(self.delay)
                return r.text
            except requests.RequestException as e:
                print(f"[ошибка] {url}: {e}", file=sys.stderr)
        return None


def crawl(cfg: dict, get: Callable[[str], str | None]) -> Iterator[dict]:
    seen_links: set[str] = set()
    produced = 0
    for start in cfg["start_urls"]:
        url, pages, visited = start, 0, set()
        while url and url not in visited and pages < cfg.get("max_pages", 20):
            visited.add(url)
            html = get(url)
            if html is None:
                break
            links, url_next = song_links(html, cfg, url)
            for link in links:
                if link in seen_links:
                    continue
                seen_links.add(link)
                page = get(link)
                rec = parse_song_page(page, cfg, link) if page else None
                if not rec or not rec["lyrics"]:
                    continue
                if not is_kazakh(rec["lyrics"]):
                    print(f"[не казахский, пропуск] {rec['title']}", file=sys.stderr)
                    continue
                yield rec
                produced += 1
                if cfg.get("max_songs") and produced >= cfg["max_songs"]:
                    return
            url, pages = url_next, pages + 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="data/songs.jsonl")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=0, help="макс. песен на сайт (0 = все)")
    a = ap.parse_args(argv)
    cfgs = json.load(open(a.config, encoding="utf-8"))
    if a.limit:
        for c in cfgs:
            c["max_songs"] = a.limit
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    seen = set()
    if os.path.exists(a.out):
        seen = {json.loads(l)["id"] for l in open(a.out, encoding="utf-8") if l.strip()}
    fetcher, n = Fetcher(a.delay), 0
    with open(a.out, "a", encoding="utf-8") as out:
        for cfg in cfgs:
            for rec in crawl(cfg, fetcher.get):
                if rec["id"] in seen:
                    continue
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                n += 1
                print(f"[{n}] {rec['source']}: {rec['title']}", file=sys.stderr)
    print(f"Готово: +{n} песен → {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
