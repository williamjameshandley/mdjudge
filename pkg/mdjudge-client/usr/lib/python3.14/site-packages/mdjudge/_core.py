"""The judgement vocabulary and its two verbs.

Envelope (documented, never validated — readers raise KeyError on drift):

  title: <text>              required — the question, phrased to be read aloud
  summary: <text>            required — the one-line form a small screen shows
  kind: judgement            stamped by request_card; the substrate filing key
  judgement_status: open | answered | expired | withdrawn
  options: [<text>, ...]     optional; stored unnumbered, numbered at render
  interrupt: open | brief    minimum availability that may show this
  expires: <iso8601 utc>     optional; companion expires_epoch for queries
  producer: <source>:<id>    namespaced reference to the blocked thing
  answer: <text>             stamped by answer_card only
  approved_sha: <sha>        the commit whose bytes were read when answering
  answered_at: <iso8601 utc>
  answered_by: <surface>

Body = the evidence, markdown. Expiry is derived at read time — an open card
past its expires is excluded from the queue and the producer must treat the
absence of an answer as the third outcome; nothing defaults to yes.
"""

from datetime import timezone

STATUSES = ("open", "answered", "expired", "withdrawn")
INTERRUPTS = ("open", "brief")

_ADMITS = {"open": ("open", "brief"), "brief": ("brief",), "silent": ()}


class AlreadyAnswered(RuntimeError):
    """The card already carries an answer — answering again would overwrite it."""


def request_card(
    editor,
    *,
    title,
    summary,
    evidence,
    producer,
    interrupt,
    options=(),
    expires=None,
    tags=(),
):
    """Create one judgement request. The sole creator; the result is invariant."""
    if interrupt not in INTERRUPTS:
        raise ValueError(interrupt)
    yaml = {
        "judgement_status": "open",
        "interrupt": interrupt,
        "producer": producer,
    }
    if options:
        yaml["options"] = [str(option) for option in options]
    if expires is not None:
        yaml["expires"] = expires.astimezone(timezone.utc).isoformat(timespec="seconds")
        yaml["expires_epoch"] = int(expires.timestamp())
    return editor.create(
        title=title,
        summary=summary,
        kind="judgement",
        yaml=yaml,
        body=evidence,
        tags=list(tags) or None,
    )


def answer_card(editor, card, *, answer, approved_sha, surface, now):
    """Stamp the answered stratum. The sole mutator of a judgement card.

    Crashes on any card whose kind is not judgement, so another vocabulary's
    card is never a mutation backdoor, and raises `AlreadyAnswered` rather
    than overwriting a recorded answer.
    """
    if card.kind != "judgement":
        raise ValueError(f"card {card.id}: kind {card.kind!r} is not a judgement")
    if card.yaml["judgement_status"] not in STATUSES:
        raise ValueError(card.yaml["judgement_status"])
    if "answer" in card.yaml:
        raise AlreadyAnswered(card.id)
    card.yaml.update(
        {
            "judgement_status": "answered",
            "answer": answer,
            "approved_sha": approved_sha,
            "answered_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "answered_by": surface,
        }
    )
    return editor.update(card, summary=card.summary)


def open_requests(db, availability, *, now):
    """Ids of open, unexpired requests admissible at the availability level.

    Availability is a display filter, not a lifecycle state — an unshown card
    stays open. Oldest first, from the substrate's git-derived first_commit.
    """
    admits = _ADMITS[availability]
    if not admits:
        return []
    placeholders = ",".join("?" * len(admits))
    rows = db.conn.execute(
        "SELECT e.id FROM entries e "
        "JOIN entry_fields s ON s.entry_rowid = e.rowid "
        "  AND s.key = 'judgement_status' AND s.value_str = 'open' "
        "JOIN entry_fields i ON i.entry_rowid = e.rowid "
        f"  AND i.key = 'interrupt' AND i.value_str IN ({placeholders}) "
        "WHERE e.kind = 'judgement' AND NOT EXISTS ("
        "  SELECT 1 FROM entry_fields x WHERE x.entry_rowid = e.rowid "
        "  AND x.key = 'expires_epoch' AND x.value_num <= ?) "
        "ORDER BY e.first_commit",
        (*admits, int(now.timestamp())),
    ).fetchall()
    return [row[0] for row in rows]
