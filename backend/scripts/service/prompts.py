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
        "reason":      "<A few entences explaining why you chose each field value: the event name, event date(s), location, discipline, and type>"
    }}"""

# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = textwrap.dedent(
    f"""
    You are a structured data extraction assistant specializing in rock climbing competitions.
    Given raw web content from a climbing gym or competition source,
    extract ONLY competition-level climbing events and return them as a JSON array.

    SCOPE — include any competition-relevant climbing events, such as:
    - Competitions in any discipline: Bouldering, Top-rope, Lead, Speed, or Mixed. 
      - Make sure we don't count a competition that has different levels to be mixed.
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
    - posts about athletes from the gym competing at an external event hosted elsewhere
      (e.g. congratulating their climbers at the IFSC World Championships, USA Climbing
      Nationals, or any other competition not hosted at or by this gym). These are athlete
      shoutouts, not events hosted by the posting gym — ignore them entirely.

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

    Author context:
    - The header may include an "Author" field: the Instagram handle or website domain that
      published the post. Use it as a host-identity signal:
      • If the Author matches (or strongly resembles) the gym or organisation running the event,
        treat all extracted events as being hosted by that entity.
      • If the Author is a parent organisation handle (e.g. @touchstoneclimbing), individual
        events may be spread across member gyms — rely on location fields and any TARGET GYM
        FILTER appended below to decide which events to keep.
      • Do NOT fabricate an event location solely from the Author; location must still be
        grounded in the post content.

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
    - Date inference: NEVER fabricate or guess an event_date, e.g., from date_posted. A date must
      be grounded in explicit textual evidence. For example, a specific date/month/day stated in the content,
      a countdown that lets you calculate forward from date_posted (e.g. "2 weeks away" posted on
      2025-10-01 → ~2025-10-15), or a clear relative reference ("this Saturday", "next month").
      If the content gives no such evidence, set event_date to null.
    - event_date must reflect the date(s) the competition itself takes place. Registration open/close
      dates, sign-up deadlines, and waitlist dates are NOT event dates — do not use them for
      event_date. If only a registration date is mentioned and no competition date can be inferred,
      set event_date to null.
    - Date attribution: a post may mention dates for multiple distinct events or rounds (e.g. a
      series listing "Event 2: March 20" and "Event 3: May 19"). Only include dates that directly
      belong to the specific event record you are extracting. Do NOT carry over dates from sibling
      events or future instalments mentioned in the same post. Each extracted record
      must have only its own event's date(s).

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


def build_extraction_prompt(
    gym_context: dict | None = None,
    known_events: list[dict] | None = None,
) -> str:
    """
    Return EXTRACTION_PROMPT, optionally extended with:

    * A ``known_events`` section listing competitions already on record for
      this gym — helps the LLM recognise sponsor shoutouts, countdowns
      without explicit dates, or any post that references a known event name.
    * A ``TARGET GYM FILTER`` hard rule when *gym_context* is provided, used
      for org-level posts that may mention multiple member-gym locations.

    gym_context should be a dict with at least a ``name`` key and optionally
    a ``city`` key — e.g. ``{"name": "Hyperion Climbing", "city": "Berkeley"}``.
    """
    prompt = EXTRACTION_PROMPT

    if known_events:
        lines = []
        for ev in known_events:
            name = ev.get("event_name") or "?"
            disc = ev.get("discipline")
            dates = ev.get("event_dates") or []
            parts = []
            if disc:
                parts.append(disc)
            if dates:
                parts.append(", ".join(str(d) for d in dates if d))
            suffix = f" ({', '.join(parts)})" if parts else ""
            lines.append(f"  - {name}{suffix}")
        known_section = textwrap.dedent(
            f"""

    ── KNOWN EVENTS AT THIS GYM ─────────────────────────────────────────────
    The following competitions are already on record for this gym.
    
    If the post content clearly relates to one of these events — even without
    explicit competition keywords (e.g. a sponsor shoutout, a countdown post,
    an athlete call-out, or a schedule update) — extract it using the matching
    known event name and appropriate type (announcement / reminder / recap).
    Do NOT use this list to fabricate dates or details not present in the post.

    Known events:
{chr(10).join(lines)}
    """
        ).rstrip()
        prompt = prompt + known_section

    if not gym_context:
        return prompt
    name = gym_context.get("name", "")
    city = gym_context.get("city", "")
    location_str = f"{name}, {city}" if city else name
    filter_section = textwrap.dedent(
        f"""

    ── TARGET GYM FILTER (hard rule — overrides all other instructions) ──────
    This post was published by a parent organisation, not by the gym itself.
    You MUST extract ONLY events whose location is: {location_str}.

    Hard rules:
    1. If an event's location field would be anything other than {location_str},
       do NOT include that event — omit it entirely.
    2. Events at sibling gyms, other venues, or unspecified locations must be
       skipped even if the post mentions them.
    3. If no events in the post are at {location_str}, return [].

    Example: if the post mentions 'Battle of the Bay at Hyperion' and the target
    gym is '{location_str}', you MUST return [] because that event is at Hyperion,
    not at {location_str}.
    """
    ).rstrip()
    return prompt + filter_section


# ── Summarize prompt ──────────────────────────────────────────────────────────

SUMMARIZE_PROMPT = textwrap.dedent(
    """
    You are a competition event description writer for a rock climbing gym.

    You will receive a set of posts (social media captions and their previously
    extracted summaries) that all relate to a single competition event.
    Your job is to write one authoritative, comprehensive summary paragraph for
    that event — the kind that would appear on an event listing page.

    Guidelines:
    - Mirror the organizer's own voice and tone as faithfully as possible.
      If they are enthusiastic and casual, match that energy; if they are
      formal, keep it professional.
    - Synthesize across ALL posts: announcements tell you format and structure,
      reminders reveal deadlines and logistics, recaps surface results and
      highlights.
    - Cover as many of the following as the posts support:
        • Competition format (e.g. bouldering, top-rope, heat structure)
        • Categories / divisions / age groups
        • Prizes, awards, or raffle
        • Schedule or key dates (registration deadline, comp day, awards)
        • Registration details (link, cost, capacity, waitlist)
        • Any unique highlights, sponsors, or community aspects worth noting
    - Do NOT invent details that are not present in the provided posts.
    - Format rules (MANDATORY):
        1. Open with 1–2 prose sentences giving the high-level overview
           (event name, gym, date, discipline).
        2. Use `#### ` to introduce each logical section (e.g. #### Categories, #### Schedule,
           #### Registration, ### Sponsors). `###` is the ONLY allowed header level.
        3. Under each section, use flat `- ` bullet lists. Each distinct item gets its
           own bullet. NEVER nest bullets (no `  - ` sub-items).
        4. Close with 1 prose sentence capturing the community vibe or call to action
           if the posts support it.
        5. Separate every section with a blank line (i.e. \\n\\n between sections).
    - When outputting the JSON value for "summary", represent every line break as \\n
      so the JSON string remains valid. Do not emit raw unescaped newlines inside the
      JSON string value.
    - Tense: use present/future for upcoming events, past tense for recaps;
      if both exist (the event was announced and has since concluded), prefer
      past tense describing the full arc.

    Output a single JSON object — no array, no code fences. The "summary" value is a
    Markdown string (escape any double quotes inside it):
    {
        "summary": "<your Markdown description>",
        "reason":  "<1-2 sentences noting which posts or details most shaped the summary>"
    }
    """
).strip()


def build_summarize_prompt_input(
    event_name: str,
    raw_events: list[dict],
) -> str:
    """
    Format *raw_events* for the user turn of the summarize LLM call.

    Each item in *raw_events* should be the dict returned by
    ``get_raw_events_for_event`` — it must carry at minimum ``type``,
    ``date_posted``, ``url``, and at least one of ``post_caption`` or
    ``summary``.
    """
    lines: list[str] = [f'Event: "{event_name}"', ""]
    for i, re in enumerate(raw_events, 1):
        post_type = (re.get("type") or "unknown").upper()
        date_posted = re.get("date_posted") or "unknown date"
        url = re.get("url") or ""
        author = re.get("post_author") or ""
        caption = (re.get("post_caption") or "").strip()
        extracted_summary = (re.get("summary") or "").strip()

        lines.append(f"── Post {i} ({post_type}  {date_posted}{f'  @{author}' if author else ''})")
        if url:
            lines.append(f"   URL: {url}")
        if caption:
            lines.append(f"   Original caption:\n{textwrap.indent(caption, '     ')}")
        if extracted_summary:
            lines.append(f"   Extracted summary: {extracted_summary}")
        lines.append("")

    return "\n".join(lines).rstrip()


MERGE_COMMANDS_PROMPT = textwrap.dedent(
    """
    You are a data normalisation assistant for rock climbing competition records.
    You will receive a JSON array of event records, each with an `id` field (database PK).
    Decide which records refer to the same real-world event and output MERGE commands.

    ── STEP 1: group by identity ────────────────────────────────────────────────
    Two records refer to the same event when ANY of the following holds:
    A. Their event_names are equivalent — same words, ignoring case, punctuation, and
       minor spelling variants (e.g. "Telegraph Turn-Up" = "Telegraph Turn Up" = "telegraph turn up").
    B. Their event_date arrays share at least one identical date AND their names are
       not clearly different events (see Step 2 blockers).
    C. One record's summary explicitly names the event from another record
       (e.g. summary says "SV Classic" and the other record is literally named "SV Classic").
       Thematic similarity is NOT enough — the exact event name must appear.

    ── STEP 2: apply hard blockers ──────────────────────────────────────────────
    Do NOT merge records that would otherwise qualify if:
    a. Their names include different edition years (e.g. "Event 2025" vs "Event 2026").
    b. Their names include different series identifiers (e.g. "Series Round 1" vs "Series Round 2").
    c. They have explicitly conflicting venues.
    d. Their names are clearly different events — two distinct proper names that do not
       refer to the same competition (e.g. "Woman Up 2026" and "Battle of the Bay 2026"
       are different events and must NEVER be merged, even if posted by the same gym).
    e. Their event_date arrays have no overlap (no shared date).

    ── STEP 3: ensure transitivity ──────────────────────────────────────────────
    If record A merges with B, and B merges with C, then A, B, and C must all appear
    in a single MERGE command — never in separate commands.

    ── STEP 4: canonical name ───────────────────────────────────────────────────
    Use the most specific proper name among the grouped records.
    Generic phrases ("Last comp of the year", "Only 2 days left…") are never canonical.

    ── OUTPUT ───────────────────────────────────────────────────────────────────
    A JSON array of MERGE commands ([] if nothing to merge):
    [
      {
        "command": "MERGE",
        "ids": [<int>, ...],
        "canonical_name": "<most specific proper event name among the grouped records, or null to auto-pick>",
        "canonical_dates": ["<ISO 8601 date(s) the event takes place; one entry per day>"] or null to auto-pick,
        "canonical_discipline": "<'bouldering' | 'top-rope' | 'lead' | 'mixed' | 'speed'> or null to auto-pick",
        "canonical_summary": "<2-4 sentence summary combining the most informative details from all merged records, or null to auto-pick>",
        "reason": "<1-2 sentences citing the specific matching names, dates, or summary text that triggered this merge>"
      }
    ]
    - Output ONLY a valid JSON array. No markdown, no explanation, no code fences.
    - Each id appears in at most one MERGE command.
    - Only include records that need merging — omit singletons.
    - ids must contain at least 2 elements.
    - Before emitting any MERGE command, verify that none of the Step 2 blockers apply.
      If a blocker applies, do not emit the command at all.
    """
).strip()
