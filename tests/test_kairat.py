from kairat.decoder import clean_lyrics, decode, fix_encoding
from kairat.parser import parse_lyrics_html

HTML = '''<div data-lyrics-container="true"><div data-exclude-from-selection="true">Contributors</div>
[Куплет 1]<br/>Строка один<br/>Строка два<br/><br/>[Припев]<br/>Припев &amp; всё</div>'''


def test_parse_html():
    t = parse_lyrics_html(HTML)
    assert "Contributors" not in t
    assert "Строка один\nСтрока два" in t and "Припев & всё" in t


def test_clean_tags():
    t = clean_lyrics(parse_lyrics_html(HTML))
    assert "[" not in t and t.startswith("Строка один")
    assert "[Припев]" in clean_lyrics(parse_lyrics_html(HTML), keep_tags=True)


def test_mojibake():
    bad = "Кайрат".encode("utf-8").decode("latin-1")
    assert fix_encoding(bad) == "Кайрат"


def test_decode_dedup_and_format():
    rec = {"title": "А", "artist": "К", "lyrics": "қалқам ғашық " * 20}
    out = list(decode([rec, dict(rec)], "chat"))
    assert len(out) == 1 and out[0]["messages"][1]["role"] == "assistant"


# ---- казахский фильтр и парсер сайтов ----
from kairat.kazakh import is_kazakh
from kairat.sites import crawl

KK = "Сені сүйдім жүрегімде\nҚалқам ғашық болдым мен\nКөзің менің өмірімде\nҰмытпаймын сені мен"
RU = "Я люблю тебя всем сердцем\nТы моя единственная\nНе забуду никогда\nЛюбовь моя навеки"


def test_is_kazakh():
    assert is_kazakh(KK) and not is_kazakh(RU) and not is_kazakh("I love you baby\nyeah yeah")


def test_decode_filters_russian():
    recs = [{"title": "a", "artist": "k", "lyrics": KK * 3},
            {"title": "b", "artist": "k", "lyrics": RU * 3}]
    assert len(list(decode(recs, "text"))) == 1
    assert len(list(decode(recs, "text", kazakh_only=False))) == 2


def test_crawl_site():
    cfg = {"name": "t", "artist": "К", "start_urls": ["http://x/list"], "link_selector": "a.s",
           "lyrics_selector": "div.l", "next_selector": "a.n"}
    pages = {
        "http://x/list": '<a class="s" href="/1">1</a><a class="s" href="/2">2</a><a class="n" href="/list2">n</a>',
        "http://x/list2": '<a class="s" href="/3">3</a>',
        "http://x/1": "<h1>Бір</h1><div class='l'>" + KK.replace("\n", "<br>") + "</div>",
        "http://x/2": "<h1>Два</h1><div class='l'>" + RU.replace("\n", "<br>") + "</div>",
        "http://x/3": "<h1>Үш</h1><div class='l'>" + KK.replace("\n", "<br>") + "</div>",
    }
    got = list(crawl(cfg, pages.get))
    assert [r["title"] for r in got] == ["Бір", "Үш"] and got[0]["artist"] == "К"


def test_link_filter_and_title_split():
    cfg = {"name": "t", "start_urls": ["http://x/l"], "link_selector": "a.s", "link_filter": "Қайрат",
           "title_selector": "h1", "title_split": " - ", "lyrics_selector": "font"}
    pages = {
        "http://x/l": '<a class="s" href="/1">Қайрат Нұртас - Ән</a><a class="s" href="/2">Басқа - Ән</a>',
        "http://x/1": "<h1>Қайрат Нұртас - Ән <small>әнінің сөздері</small></h1><font>" + KK.replace("\n", "<br>") + "</font>",
        "http://x/2": "<h1>Басқа - Ән</h1><font>" + KK.replace("\n", "<br>") + "</font>",
    }
    got = list(crawl(cfg, pages.get))
    assert len(got) == 1 and got[0]["artist"] == "Қайрат Нұртас" and got[0]["title"] == "Ән"
