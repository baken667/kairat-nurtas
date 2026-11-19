# kairat-nurtas — датасет песен для обучения ИИ

```bash
pip install -r requirements.txt
export GENIUS_TOKEN=...                       # https://genius.com/api-clients
python -m kairat.parser --artist "Kairat Nurtas" --out data/songs.jsonl   # сбор через Genius (возобновляемый)
python -m kairat.sites --config sources.json --out data/songs.jsonl       # сбор с казахстанских сайтов
python -m kairat.decoder data/songs.jsonl data/train.jsonl --format chat  # text | chat | alpaca | raw
pytest
```

- `parser.py` — Genius API → страницы текстов → сырой JSONL (id, title, artist, album, release_date, url, lyrics).
- `sites.py` — парсер казахстанских сайтов по конфигу (`sources.example.json`): списки песен → страницы → JSONL. Учитывает robots.txt, пропускает не-казахские тексты.
- `kazakh.py` — детектор казахского (доли букв ә ғ қ ң ө ұ ү һ і и строк с ними).
- `decoder.py` — чинит кодировку/HTML-сущности, убирает мусор и теги секций, дедуплицирует, пишет в нужный формат. По умолчанию оставляет только казахские тексты (`--any-language` отключает).

Тексты песен защищены авторским правом: проверьте, что у вас есть право использовать их для обучения.
