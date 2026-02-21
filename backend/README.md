# competition-tracker

## Prerequisites:

```shell
crawl4ai-setup
crawl4ai-doctor

playwright install firefox
```

## Pipeline

1. **Extract** from IG/website/calendar in `posts`

```shell
# for instagram post extraction
python scripts/extract_instagram.py \
--profile pacificpipe \
--gym pacific-pipe \
--since 2025-10-01
# --until 2026-02-19

# for website article extraction
python scripts/extract_website.py \
--gym bridges-rock-gym \
--url https://www.bridgesrockgym.com/events
```

2. **Parse** into unified structured data to `raw_events`

```shell
python scripts/parse.py \
--gym pacific-pipe \
--include-org-posts # (also parse unprocessed posts from the org account)
```

3. **Merge** : constructing `events` from `raw_events` 

```shell
python scripts/merge.py \
--gym pacific-pipe
```

4. **Manual merge** `events` entries

```shell
python scripts/merge_manual.py \
--gym hyperion-climbing \
--from 74 75 \
--to 73

# to-do: we may need to support cross-gym merge in the future
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

# OR
docker compose exec db psql -U crux -d competition_tracker -c "\dt"
```

## To-do

- [ ] An eval playground to test:
    - [ ] mosaic: ig
    - [ ] bridges: ig + website
    - [ ] touchstone gyms: gyms's ig + org's ig
- [ ] Set up an additional pipe to be able to infer whther this event is professional or non-professional