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
        "discipline":  "<'bouldering' | 'top-rope' | 'lead' | 'mixed' | 'speed' | null>",
        "type":        "<'announcement' | 'reminder' | 'recap'>",
        "summary":     "<2-4 sentence summary; see summary rules below>" """

# Extraction output — base fields + single-source attribution
_EXTRACTION_SCHEMA = f"""\
    {{
{_BASE_EVENT_FIELDS},
        "date_posted": "<ISO 8601 date the source was posted; null if unknown>",
        "platform":    "<'instagram' | 'website' | 'others'>",
        "url":         "<URL of the source post or page>",
        "reason":      "<1-3 sentences explaining why you chose each field value: the event name, date(s), location, discipline, and type>"
    }}"""

# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = textwrap.dedent(
    f"""
    You are a structured data extraction assistant specializing in rock climbing competitions.
    Given raw web content from a climbing gym or competition source,
    extract ONLY competition-level climbing events and return them as a JSON array.

    SCOPE — include any competition-relevant climbing events, such as:
    - Competitions in any discipline: Bouldering, Top-rope, Lead, Speed, or Mixed
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
    - Year inference: when the source text mentions a date without an explicit year (e.g. "November 9"),
      derive the year from date_posted or surrounding context. An upcoming event mentioned in a
      2025-10-01 post most likely falls in 2025 or early 2026; do NOT default to an arbitrary past
      year. If the year cannot be confidently inferred, omit the date entirely (use null) rather
      than guessing.

    Summary rules: keep summaries between 2–4 sentences. Tailor content by type:
    - announcement: Must include the competition discipline (bouldering/top-rope/lead/speed/mixed),
      date and location/gym, registration or sign-up details if available, and any eligibility
      requirements (age category, skill level, etc.).
    - reminder: Must include what the follow-up is about (deadline, schedule change, countdown,
      waitlist), the event it relates to, and any updated dates or details mentioned.
    - recap: Must include the outcome (results, winner, podium), the competition it covers,
      and any athletes, notable performances, or media highlights mentioned in the content.
"""
).strip()

MERGE_COMMANDS_PROMPT = textwrap.dedent(
    """
    You are a data normalisation assistant for rock climbing competition records.
    You will receive a JSON array of event records, each identifiable by its `id` field
    (the database primary key). Your only job is to decide which records refer to the same
    real-world event and output a list of MERGE commands.

    MERGE RULES — apply in priority order:
    0. Hard blockers — NEVER merge when any of the following apply:
       a. Different edition year: events sharing a name but with different year numbers
          (e.g. "Climbing Event Name 2025" vs "Climbing Event Name 2026") are distinct annual
          editions.
       b. Different numbered or subtitled event within a series: if the names include
          distinct identifiers such as event numbers, round names, or subtitles
          (e.g. "Climbing Series - Event A" vs "Climbing Series - Event B"), 
          they are separate events even if they share a parent series name, 
          appeared in the same source post, or have overlapping dates.
       c. Conflicting venue.
    1. Identical event_name (same year, or no year present) → always merge.
    2. Identical event_date(s) + same location → always merge.
    3. Equivalent names (share a distinctive proper noun / nickname) + same venue or
       adjacent dates (within ~3 days) → merge.
    4. A record whose summary explicitly names the proper event name of another record
       (e.g. summary says "the bouldering comp of the summer hits Sunnyvale" and another
       record is named "SV Classic" at Sunnyvale on the same date) → merge, even if the
       event_names differ.
    5. Generic descriptors ("Last Bouldering Competition of the Year",
       "Summer Bouldering Competition", "Only 2 days left…") are NOT canonical names.
       When merging such a record with one that has a proper event name, the proper name
       is canonical.

    Date note: event_date values may be off by 1–2 days due to extraction noise.

    Output format — a JSON array of MERGE commands, or [] if nothing to merge:
    [
      {
        "command": "MERGE",
        "ids": [<int>, ...],
        "canonical_name": "<the real proper event name to use, or null to auto-pick>",
        "reason": "<1-2 sentences why>"
      }
    ]

    Rules:
    - Output ONLY a valid JSON array. No markdown, no explanation, no code fences.
    - Each `id` must appear in at most one MERGE command.
    - Only include records that need merging — omit singletons entirely.
    - ids must contain at least 2 elements.
    - Set canonical_name to the most specific proper event name present in the grouped
      records. Use null only if all names are equally generic.
    """
).strip()
