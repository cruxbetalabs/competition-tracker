let's go. 

let's build up our ground truth dataset for these cases for now, that is running the following command sequentially, so that we get a database copy, then we export them into json format, so i can fillin with the correct value to build up the groundtruth dataset.

general eval rules:

- for `parse.py`: we should get `raw_events` entries such that:
    - has `event_name` + `event_dates` + `discipline` + `type`  roughly identified
    - the `reason` field is reasonable and makes no obvious mistake
- for `merge.py`: we should get `events` entries such that:
    - the list of commands that output to the merge executor is right

## Mosaic 

```shell
# We already have posts scraped for Mosaic Boulders (gym_id=95)

python scripts/parse.py \
--gym mosaic-boulders

python scripts/merge.py \
--gym mosaic-boulders
```

## Bridges

```shell
# We already have posts scraped for Bridges Rock Gym (gym_id=1)

python scripts/parse.py \
--gym bridges-rock-gym

python scripts/merge.py \
--gym bridges-rock-gym
```

## Hyperion Climbing & Pac Pipe

```shell
# We already have posts scraped for Hyerion Climbing (gym_id=18)
# Since it's a Touchstone gym, so we will also consider Touchstone's posts (organization_id=4)

python scripts/parse.py \
--gym hyperion-climbing \
--include-org-posts

python scripts/merge.py \
--gym hyperion-climbing
```

```shell
python scripts/parse.py \
--gym pacific-pipe \
--include-org-posts

python scripts/merge.py \
--gym pacific-pipe

# The event name is derived from the title of the series mentioned in the content. The event dates are explicitly stated as February 15 for the qualifiers and April 19 for the finals. The location is confirmed as Pacific Pipe, Oakland, which matches the target gym filter. The discipline is speed climbing, and the type is an announcement since it is the first reveal of the event details.
```

## Benchmark SF

```shell
python scripts/parse.py \
--gym benchmark-climbing-san-francisco \
--include-org-posts

python scripts/merge.py \
--gym benchmark-climbing-san-francisco

python scripts/merge_manual.py \
--gym benchmark-climbing-san-francisco \
--from 106 \
--to 105
# because this:
# 105	191	TRUE	Halloween Dyno Comp + Costume Contest	{2025-10-30}	mixed	Join us on Thursday, October 30th for Benchmark’s third-annual Halloween Dyno Comp + Costume Contest! The event features beginner, intermediate, and advanced categories, with prizes for top climbers and costumes. This event is free for members, while non-members need to purchase a $30 ticket.	Auto-picked by executor (LLM left null): canonical_dates, canonical_discipline, canonical_summary.	2026-02-21 06:05:33.15664+00
# 106	191	TRUE	Spooky Dyno Comp and Costume Contest	{2025-10-31}	mixed	Join us for the spookiest dyno competition and costume contest at Benchmark Climbing, San Francisco on October 31, 2025! This event features free pizza, amazing prizes, and climbing in costumes. Registration is required, with free entry for members and a $30 fee for non-members.	Auto-picked by executor (LLM left null): canonical_dates, canonical_discipline, canonical_summary.	2026-02-21 06:05:33.15664+00
```