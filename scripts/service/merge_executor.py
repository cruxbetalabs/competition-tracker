"""
MergeExecutor — deterministic command executor for event merging.

Receives the original events list and a list of MERGE commands produced by the
LLM, then applies them using fixed field-selection rules so that no LLM call
ever rewrites field values.

Command schema (produced by MERGE_COMMANDS_PROMPT):
    { "command": "MERGE", "ids": [<int>, ...], "canonical_name": "<str | null>", "reason": "<str>" }

Records not referenced by any command are emitted as singletons.

Output record schema:
    {
        "event_name":  str,
        "event_date":  list[str | None],
        "location":    str | None,
        "discipline":  str | None,
        "summary":     str,
        "reason":      str | None,
        "posts":       [<full original event record>, ...]
    }
"""

from __future__ import annotations


# ── Field-selection rules ─────────────────────────────────────────────────────


def _pick_event_name(records: list[dict], canonical_name: str | None = None) -> str:
    """
    Use canonical_name from the MERGE command when provided.
    Otherwise prefer a proper name (one that isn't a generic descriptor) by
    filtering out names that look like generic phrases, then falling back to
    the longest remaining name.
    """
    if canonical_name:
        return canonical_name

    # Heuristic: names that start with generic words are lower-priority
    _GENERIC_PREFIXES = (
        "last ",
        "first ",
        "only ",
        "summer ",
        "winter ",
        "spring ",
        "fall ",
        "the last ",
        "the first ",
    )

    names = [r.get("event_name") or "" for r in records]
    proper = [
        n
        for n in names
        if n and not any(n.lower().startswith(p) for p in _GENERIC_PREFIXES)
    ]
    candidates = proper if proper else names
    return max(candidates, key=len)


def _pick_event_date(records: list[dict]) -> list:
    """Union of all non-null dates across records, sorted.
    Falls back to [null] only if every record has no date.
    Accepts both 'event_date' (extraction output) and 'event_dates' (DB column name).
    """
    dates: set[str] = set()
    for r in records:
        for d in r.get("event_date") or r.get("event_dates") or []:
            if d:
                dates.add(d)
    return sorted(dates) if dates else [None]


def _pick_first_non_null(records: list[dict], key: str):
    """Return the first non-null value for *key* across records."""
    for r in records:
        v = r.get(key)
        if v is not None:
            return v
    return None


def _pick_summary(records: list[dict]) -> str:
    """Longest summary carries the most information."""
    return max(
        (r.get("summary") or "" for r in records),
        key=len,
    )


def _extract_posts(record: dict) -> list[dict]:
    """Return the original source records embedded in *record*.

    • If the record was already merged (has a "posts" key), return those
      embedded post objects verbatim.
    • Otherwise the record itself is a raw extraction result; return it
      as the sole post.
    """
    if "posts" in record:
        return list(record["posts"])
    # Raw extraction record — include the whole thing as a post.
    return [record]


# ── Executor ──────────────────────────────────────────────────────────────────


def manual_merge(
    events: list[dict],
    from_ids: list[int],
    to_id: int,
) -> list[dict]:
    """
    Manually merge one or more records into a single target record.

    The target record (``to_id``) is authoritative for ``event_name`` —
    its name always wins. All other fields are resolved with the same rules
    used by ``apply_commands`` (e.g. union of dates, first non-null location,
    recap > reminder > announcement for type, longest summary).
    The ``to`` record is placed first so field-selection rules naturally
    prefer its values.

    Parameters
    ----------
    events : list[dict]
        The full list of event records, each must carry an ``id`` field
        (the DB primary key).
    from_ids : list[int]
        IDs of records to fold into the target.
    to_id : int
        ID of the target (destination) record.

    Returns
    -------
    list[dict]
        New event list with the merged record in place of ``to_id``
        and ``from_ids`` records removed.
    """
    # ── Build id map ──────────────────────────────────────────────────────────
    id_map: dict[int, dict] = {e["id"]: e for e in events if "id" in e}

    # ── Validate ──────────────────────────────────────────────────────────────
    if to_id not in id_map:
        raise ValueError(f"to_id {to_id} not found in events.")

    bad = [i for i in from_ids if i not in id_map]
    if bad:
        raise ValueError(f"from_ids {bad} not found in events.")

    if to_id in from_ids:
        raise ValueError(f"to_id {to_id} must not appear in from_ids.")

    # ── Merge ─────────────────────────────────────────────────────────────────
    # Put the 'to' record first so _pick_first_non_null etc. prefer it.
    to_record = id_map[to_id]
    from_records = [id_map[i] for i in from_ids]
    all_records = [to_record] + from_records

    # The target's name is always canonical.
    canonical_name = to_record.get("event_name") or None

    # Preserve the to-record's existing reason and append the manual-merge note.
    original_reason = to_record.get("merge_reason") or to_record.get("reason") or None
    manual_note = f"Manually merged {from_ids} → {to_id}."
    reason = f"{original_reason} {manual_note}" if original_reason else manual_note

    merged_record = _to_output(
        records=all_records,
        reason=reason,
        canonical_name=canonical_name,
    )

    print(
        f"  [manual_merge] {from_ids} → {to_id}  "
        f"name={merged_record['event_name']!r}  "
        f"({len(merged_record['posts'])} post(s))"
    )

    # ── Rebuild list ──────────────────────────────────────────────────────────
    removed = set(from_ids)
    output: list[dict] = []
    for event in events:
        eid = event.get("id")
        if eid == to_id:
            output.append(merged_record)
        elif eid not in removed:
            output.append(_to_output(records=[event], reason=None))

    return output


def apply_commands(events: list[dict], commands: list[dict]) -> list[dict]:
    """
    Apply a list of MERGE commands to *events* and return the merged result.

    Parameters
    ----------
    events : list[dict]
        The original extracted event records, each must carry an ``id`` field
        (the DB primary key) used by the LLM to reference them.
    commands : list[dict]
        MERGE command dicts as produced by the LLM.

    Returns
    -------
    list[dict]
        Merged event records preserving original field values.
    """
    if not commands:
        # Nothing to merge — wrap every record as a singleton
        return [_to_output(records=[e], reason=None) for e in events]

    # ── Build id → record map ─────────────────────────────────────────────────
    id_map: dict[int, dict] = {e["id"]: e for e in events if "id" in e}

    # ── Validate commands ─────────────────────────────────────────────────────
    merged_ids: set[int] = set()
    valid_commands: list[dict] = []

    for cmd in commands:
        if cmd.get("command") != "MERGE":
            print(f"  [executor] Unknown command {cmd.get('command')!r} — skipping.")
            continue

        ids: list[int] = cmd.get("ids", [])

        if len(ids) < 2:
            print(f"  [executor] MERGE with < 2 ids {ids} — skipping.")
            continue

        unknown = [i for i in ids if i not in id_map]
        if unknown:
            print(f"  [executor] MERGE ids {unknown} not found in id_map — skipping.")
            continue

        overlap = merged_ids & set(ids)
        if overlap:
            print(f"  [executor] MERGE ids {sorted(overlap)} already used — skipping.")
            continue

        merged_ids.update(ids)
        valid_commands.append(cmd)

    # ── Build output ──────────────────────────────────────────────────────────
    output: list[dict] = []

    # 1. Apply each valid MERGE command
    for cmd in valid_commands:
        ids = cmd["ids"]
        records = [id_map[i] for i in ids]
        reason = cmd.get("reason")
        canonical_name = cmd.get("canonical_name") or None
        result = _to_output(
            records=records, reason=reason, canonical_name=canonical_name
        )
        output.append(result)
        print(
            f"  [executor] MERGE {ids} → {result['event_name']!r}  "
            f"({len(result['posts'])} post(s))"
        )

    # 2. Emit untouched records as singletons
    for event in events:
        if event.get("id") not in merged_ids:
            output.append(_to_output(records=[event], reason=None))

    return output


def _to_output(
    records: list[dict],
    reason: str | None,
    canonical_name: str | None = None,
) -> dict:
    """Combine *records* into a single output event dict."""
    posts = []
    for r in records:
        posts.extend(_extract_posts(r))

    return {
        "event_name": _pick_event_name(records, canonical_name=canonical_name),
        "event_date": _pick_event_date(records),
        "location": _pick_first_non_null(records, "location"),
        "discipline": _pick_first_non_null(records, "discipline"),
        "summary": _pick_summary(records),
        "reason": reason,
        "posts": posts,
    }
