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
--gym great-western-power-company \
--include-org-posts 
# DO NOT include this if the gym 
# doesn't have a parent organzation
```

3. **Merge** : constructing `events` from `raw_events` 

```shell
python scripts/merge.py \
--gym great-western-power-company
```

4. **Manual Merge** `events` entries

```shell
python scripts/merge.py \
--gym hyperion-climbing \
--from 74 75 \
--to 73

# to-do: we may need to support cross-gym merge in the future
```

5. **Summarize** : regenerate a rich event summary from its source posts

```shell
python scripts/summarize.py \
--gym mosaic-boulders \
--event-name "Telegraph Turn-Up 2026"
```

6. **Track** : workflow to fetch new posts and create/merge events

```shell
# for instagram post extraction
python scripts/extract_instagram.py \
--profile mosaicboulders \
--gym mosaic-boulders \
--since 2026-02-20 # get the date of lateset post we fetched

python scripts/parse.py \
--gym mosaic-boulders

python scripts/merge.py \
--gym mosaic-boulders

python scripts/merge.py \
--gym mosaic-boulders \
--from 109 \
--to 31

python scripts/summarize.py \
--gym mosaic-boulders \
--event-name "Telegraph Turn-Up 2026"
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

- [ ] write a script that migration the gyms's source + orgianzations source data to database?
    - [ ] create a `source` database
- [ ] Build an unified `extract.py` that automatically extract posts given a gym's slug
- [ ] currently when parsing, we skip posts that already has a mapping `raw_event`. but if that's not a event, we are always reparsing the non-event posts. we should find a good way for avoiding this duplicated parse.
- [ ] An eval playground to test:
    - [ ] mosaic: ig
    - [ ] bridges: ig + website
    - [ ] touchstone gyms: gyms's ig + org's ig
- [ ] Set up an additional pipe to be able to infer whther this event is professional or non-professional