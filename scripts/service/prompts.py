import textwrap

_JSON_OUTPUT_RULE = (
    "Output ONLY a valid JSON array. No markdown, no explanation, no code fences."
)

# ── Shared schema ─────────────────────────────────────────────────────────────
# Core event fields present in BOTH extraction and merge output.
# Defined as a plain string so its braces are never treated as f-string
# format specs when interpolated into a prompt f-string.
_BASE_EVENT_FIELDS = """\
        "event_name":  "<canonical event name>",
        "event_date":  ["<ISO 8601 date(s) the event takes place; one entry per day; null if unknown>"],
        "location":    "<gym or venue name; null if unknown>",
        "discipline":  "<'bouldering' | 'top-rope' | 'lead' | 'mixed' | null>",
        "type":        "<'announcement' | 'reminder' | 'recap'>",
        "summary":     "<2-4 sentence summary; see summary rules below>" """

# Extraction output — base fields + single-source attribution
_EXTRACTION_SCHEMA = f"""\
    {{
{_BASE_EVENT_FIELDS},
        "date_posted": "<ISO 8601 date the source was posted; null if unknown>",
        "platform":    "<'instagram' | 'website' | 'others'>",
        "url":         "<URL of the source post or page>",
        "raw_media":   ["<image or video URLs found in the source; empty array if none>"]
    }}"""

# Merge output — same base fields + aggregated posts list
_MERGE_SCHEMA = f"""\
    {{
{_BASE_EVENT_FIELDS},
        "reason":  "<1-3 sentences explaining why these records were grouped as one event>",
        "posts": [
            {{
                "url": "<source post or page URL>"
            }}
        ]
    }}"""

# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = textwrap.dedent(
    f"""
    You are a structured data extraction assistant specializing in rock climbing competitions.
    Given raw web content from a climbing gym or competition source,
    extract ONLY competition-level climbing events and return them as a JSON array.

    SCOPE — include any competition-relevant climbing events, such as:
    - Competitions in any discipline: Bouldering, Top-rope, Lead, or Mixed
    - Onsight / redpoint series, league seasons, or recurring scored events
    - Qualifier events and finals rounds tied to a competition
    - Competition-focused training clinics, mock comps, or coaching sessions
    - Awards ceremonies, results announcements, or podium events tied to a competition
    - Any other event that is directly related to organized competitive climbing

    Ignore content that has no connection to organized competitive climbing, such as:
    - general open gym sessions,
    - yoga classes, kids programs,
    - route-setting announcements not tied to a comp,
    - merchandise sales, gym closures, fundraisers, or purely social events.

    Each item in the array must follow this exact schema:
{_EXTRACTION_SCHEMA}

    Type rules — classify by where the event sits in its lifecycle relative to date_posted:
    - announcement: The event has not yet happened and this is the first or primary reveal
      (e.g. event launch, registration opening, lineup drop, series kickoff).
    - reminder: The event has not yet happened but this is a follow-up post
      (e.g. countdown, deadline alert, schedule change, waitlist update, "one week out").
    - recap: The event has already taken place
      (e.g. results, podium, winner announcement, highlight reel, photo dump).
    Use date_posted and event_date together to determine whether the event is upcoming or past.
    When event_date is unknown, infer from context (e.g. past-tense language → recap).

    General rules:
    - {_JSON_OUTPUT_RULE}
    - If no qualifying competition events are found, return an empty array: []
    - If a field cannot be determined from the content, use null.
    - For date_posted, use the most specific date available; if unavailable use null.
    - Extract every distinct qualifying competition event or update you can identify.
    - For raw_media, collect any image or video URLs present in the content; use an empty array if none.

    Summary rules: keep summaries between 2–4 sentences. Tailor content by type:
    - announcement: Must include the competition discipline (bouldering/top-rope/lead/mixed),
      date and location/gym, registration or sign-up details if available, and any eligibility
      requirements (age category, skill level, etc.).
    - reminder: Must include what the follow-up is about (deadline, schedule change, countdown,
      waitlist), the event it relates to, and any updated dates or details mentioned.
    - recap: Must include the outcome (results, winner, podium), the competition it covers,
      and any athletes, notable performances, or media highlights mentioned in the content.
"""
).strip()

MERGE_PROMPT = textwrap.dedent(
    f"""
    You are a data normalisation assistant for rock climbing competition records.
    You will receive a JSON array of extracted event records. Multiple records may
    refer to the same real-world competition (e.g. an announcement post, a reminder
    post, and a recap post all about the same event).

    Your task: group records that refer to the same real-world event and return a
    consolidated JSON array where each item represents one distinct real-world event.

    Two records belong to the same event when they share the same competition name
    AND the same approximate date(s) AND the same gym/venue (if determinable).
    When in doubt, keep records separate rather than merging incorrectly.

    Each item in the output array must follow this exact schema:
{_MERGE_SCHEMA}

    Rules:
    - {_JSON_OUTPUT_RULE}
    - For each grouped source record, include only its url in the posts array — omit all other fields.
    - Preserve an entry for every source record in the posts array of its group — do not discard any.
    - A record that cannot be matched to any other goes into its own group (posts array of length 1); set reason to null for singleton groups.
    - For reason, briefly explain what signal(s) led to grouping (e.g. same event name, overlapping dates, same venue). Use no more than 3 sentences.
    - event_date should be the union of all dates found across grouped records, deduplicated and sorted.
    - For the summary, synthesise the most informative description possible from all grouped records.
    - Do not invent information not present in the source records.
    - If you have high confidence that all records are already distinct events with no duplicates
      (i.e. nothing needs to be merged), return an empty array [] instead of re-emitting the records.
      The caller will treat [] as a "no-op" signal and keep the original input unchanged.
"""
).strip()
