let's go. 

let's build up our ground truth dataset for these cases for now, that is running the following command sequentially, so that we get a database copy, then we export them into json format, so i can fillin with the correct value to build up the groundtruth dataset.

general eval rules:

- for `parse.py`: we should get `raw_events` entries such that:
    - has `event_name` + `event_dates` + `discipline` + `type`  roughly identified
    - the `reason` field is reasonable and makes no obvious mistake
- for `merge.py`: we should get `events` entries such that

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

## Hyperion Climbing

```shell
# We already have posts scraped for Hyerion Climbing (gym_id=18)
# Since it's a Touchstone gym, so we will also consider Touchstone's posts (organization_id=4)

python scripts/parse.py \
--gym bridges-rock-gym \
--include-org-posts

python scripts/merge.py \
--gym bridges-rock-gym
```






