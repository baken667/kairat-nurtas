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
    rec = {"title": "А", "artist": "К", "lyrics": "строка " * 20}
    out = list(decode([rec, dict(rec)], "chat"))
    assert len(out) == 1 and out[0]["messages"][1]["role"] == "assistant"
