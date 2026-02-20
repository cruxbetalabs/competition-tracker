# competition-tracker

## Pipeline

1. **Extract** from IG/website/calendar in `posts`

```shell
python scripts/extract_instagram.py \
--gym bridgesrockgym \
--since 2025-10-01 \
--until 2026-02-19

python scripts/extract_website.py \
--gym bridgesrockgym \
--url https://www.bridgesrockgym.com/events
```

2. **Parse** into unified structured data to `raw_events`

```shell
python scripts/parse.py \
--gym bridgesrockgym
```

3. **Merge** : constructing `events` from `raw_events` 

```shell
python scripts/merge.py \
--gym bridgesrockgym
```

4. **Manual merge** `events` entries

```shell
python scripts/merge_manual.py \
--gym bridgesrockgym \
--from 2 6 \
--to 11
```

## Database connection

```shell
docker compose up -d # start
docker compose ps # status
docker compose down -v # stop
```

```shell
# test connection
python -c \
"from scripts.service.db import connect; c = connect(); print('OK'); c.close()"
```
