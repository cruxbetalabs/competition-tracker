-- competition-tracker schema
-- Applied automatically on first container start via docker-entrypoint-initdb.d
--
-- Table hierarchy
-- ───────────────
--   organizations
--     └─ gyms
--          └─ posts        raw scraped content (*_posts.json)
--          └─ events       merged events       (*_events_merged.json)
--               └─ raw_events  LLM-parsed events (*_events.json)
--                              post_id  → posts.id   (which post it came from)
--                              event_id → events.id  (which merged event it belongs to)

-- ── organizations ─────────────────────────────────────────────────────────────
-- Parent chains that own one or more gym locations.
-- e.g. "Touchstone", "Movement", "Benchmark"
CREATE TABLE IF NOT EXISTS organizations (
    id         SERIAL PRIMARY KEY,
    slug       TEXT UNIQUE NOT NULL,   -- e.g. "touchstone"
    name       TEXT UNIQUE NOT NULL,   -- e.g. "Touchstone"
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── gyms ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gyms (
    id               SERIAL PRIMARY KEY,
    slug             TEXT UNIQUE NOT NULL,   -- e.g. "benchmarkclimbing"
    name             TEXT,                   -- e.g. "Benchmark Climbing"
    address          TEXT,
    city             TEXT,
    organization_id  INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    google_plus_code TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gyms_organization_id ON gyms (organization_id);

-- ── posts ─────────────────────────────────────────────────────────────────────
-- Raw scraped content produced by extract_instagram.py / extract_website.py
-- and stored in *_posts.json.
CREATE TABLE IF NOT EXISTS posts (
    id               SERIAL PRIMARY KEY,
    gym_id           INTEGER REFERENCES gyms(id)          ON DELETE SET NULL,
    organization_id  INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    -- at least one of gym_id / organization_id should be set;
    -- org-level posts (e.g. @touchstoneclimbing) may have no specific gym

    url         TEXT UNIQUE NOT NULL,  -- canonical source URL
    platform    TEXT,                  -- 'instagram' | 'website' | 'others'
    caption     TEXT,
    media_urls  TEXT[],
    timestamp   TIMESTAMPTZ,

    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_gym_id          ON posts (gym_id);
CREATE INDEX IF NOT EXISTS idx_posts_organization_id ON posts (organization_id);
CREATE INDEX IF NOT EXISTS idx_posts_platform        ON posts (platform);

-- ── events ────────────────────────────────────────────────────────────────────
-- Merged event records produced by merge_executor / merge.py.
-- raw_events rows point back here via event_id once the merge step runs.
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    gym_id       INTEGER REFERENCES gyms(id) ON DELETE SET NULL,

    event_name   TEXT NOT NULL,
    event_dates  DATE[],              -- union of all dates across merged raw_events
    discipline   TEXT CHECK (discipline IN ('bouldering', 'top-rope', 'lead', 'mixed', 'speed')),
    summary      TEXT,
    merge_reason TEXT,                -- "reason" field from merge_executor
    hidden       BOOLEAN DEFAULT TRUE, -- hide from public view until manually approved

    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_gym_id    ON events (gym_id);
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

    event_name   TEXT,
    event_dates  DATE[],
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
CREATE INDEX IF NOT EXISTS idx_raw_events_post_id  ON raw_events (post_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_event_id ON raw_events (event_id);
