# kairat-nurtas — датасет песен для обучения ИИ

```bash
pip install -r requirements.txt
export GENIUS_TOKEN=...                       # https://genius.com/api-clients
python -m kairat.parser --artist "Kairat Nurtas" --out data/songs.jsonl   # сбор (возобновляемый)
python -m kairat.decoder data/songs.jsonl data/train.jsonl --format chat  # text | chat | alpaca | raw
pytest
```

- `parser.py` — Genius API → страницы текстов → сырой JSONL (id, title, artist, album, release_date, url, lyrics).
- `decoder.py` — чинит кодировку/HTML-сущности, убирает мусор и теги секций, дедуплицирует, пишет в нужный формат.

Тексты песен защищены авторским правом: проверьте, что у вас есть право использовать их для обучения.
