-- competition-tracker schema
-- Applied automatically on first container start via docker-entrypoint-initdb.d
--
-- Table hierarchy
-- ───────────────
--   gyms
--     └─ posts        raw scraped content (*_posts.json)
--     └─ events       merged events       (*_events_merged.json)
--          └─ raw_events  LLM-parsed events (*_events.json)
--                         post_id  → posts.id   (which post it came from)
--                         event_id → events.id  (which merged event it belongs to)

-- ── gyms ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gyms (
    id               SERIAL PRIMARY KEY,
    slug             TEXT UNIQUE NOT NULL,   -- e.g. "benchmarkclimbing"
    address          TEXT,
    city             TEXT,
    state            TEXT,
    organization     TEXT,
    google_plus_code TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── posts ─────────────────────────────────────────────────────────────────────
-- Raw scraped content produced by extract_instagram.py / extract_website.py
-- and stored in *_posts.json.
CREATE TABLE IF NOT EXISTS posts (
    id          SERIAL PRIMARY KEY,
    gym_id      INTEGER REFERENCES gyms(id) ON DELETE SET NULL,

    url         TEXT UNIQUE NOT NULL,  -- canonical source URL
    platform    TEXT,                  -- 'instagram' | 'website' | 'others'
    caption     TEXT,
    media_urls  TEXT[],
    timestamp   TIMESTAMPTZ,

    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_gym_id   ON posts (gym_id);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts (platform);

-- ── events ────────────────────────────────────────────────────────────────────
-- Merged event records produced by merge_executor / merge.py.
-- raw_events rows point back here via event_id once the merge step runs.
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    gym_id       INTEGER REFERENCES gyms(id) ON DELETE SET NULL,

    gym          TEXT,                -- gym slug (denormalised for easy filtering)
    event_name   TEXT NOT NULL,
    event_dates  DATE[],              -- union of all dates across merged raw_events
    location     TEXT,
    discipline   TEXT CHECK (discipline IN ('bouldering', 'top-rope', 'lead', 'mixed')),
    summary      TEXT,
    merge_reason TEXT,                -- "reason" field from merge_executor

    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_gym_id    ON events (gym_id);
CREATE INDEX IF NOT EXISTS idx_events_gym        ON events (gym);
CREATE INDEX IF NOT EXISTS idx_events_discipline ON events (discipline);

-- ── raw_events ────────────────────────────────────────────────────────────────
-- One row per LLM-extracted event record (*_events.json).
-- post_id  links back to the source post that generated this extraction.
-- event_id links forward to the merged event this raw record belongs to
--          (NULL until the merge step has been run and loaded).
CREATE TABLE IF NOT EXISTS raw_events (
    id           SERIAL PRIMARY KEY,
    gym_id       INTEGER REFERENCES gyms(id)    ON DELETE SET NULL,
    post_id      INTEGER REFERENCES posts(id)   ON DELETE SET NULL,
    event_id     INTEGER REFERENCES events(id)  ON DELETE SET NULL,

    gym          TEXT,      -- gym slug (denormalised for easy filtering)
    event_name   TEXT,
    event_dates  DATE[],
    location     TEXT,
    discipline   TEXT,
    type         TEXT,
    summary      TEXT,
    reason       TEXT,      -- LLM's explanation for the extracted field values

    date_posted  DATE,
    platform     TEXT,
    url          TEXT,      -- source post URL (matches posts.url when post_id is set)
    raw_media    TEXT[],    -- image / video URLs copied verbatim

    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_events_gym_id   ON raw_events (gym_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_gym      ON raw_events (gym);
CREATE INDEX IF NOT EXISTS idx_raw_events_post_id  ON raw_events (post_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_event_id ON raw_events (event_id);
