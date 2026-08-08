"""HTTP client for the judgement queue: ask, wait, resolve, availability.

Composable Python in the post-MCP house shape — an agent calls these from a
REPL, a hook, or another service; there is no CLI. The one-liner gate:

    python -c 'from mdjudge.client import ask, wait
    print(wait(ask("Merge PR 14?", options=["merge", "hold"])))'

``wait`` returns Will's answer (possibly free text outside the options —
honour it), raises `Expired` on the third outcome (nothing defaults to yes),
and `TimeoutError` on the caller's own deadline. Check `availability()`
first: ``silent`` means nothing will be shown, so do not post.

stdlib only, so compute hosts install one module. ``$MDJUDGE_URL`` overrides
the service (default the lovelace front door); TLS is unverified while the
intranet CA remains a browser-side install — the bearer seal replaces this
posture.
"""

import json
import os
import socket
import ssl
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("MDJUDGE_URL", "https://lovelace.fritz.box/judge")
_CONTEXT = ssl._create_unverified_context()


class Expired(RuntimeError):
    """The request lapsed unanswered — the third outcome, never a default yes."""


def _call(method, path, payload=None):
    request = urllib.request.Request(
        f"{BASE}/api/{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, context=_CONTEXT, timeout=30) as response:
        return json.load(response)


def availability():
    """The shared open | brief | silent state Will sets from any surface."""
    return _call("GET", "availability")["level"]


def set_availability(level):
    """Set the shared state (a surface act; producers only read it)."""
    return _call("POST", "availability", {"level": level})["level"]


def ask(
    title,
    *,
    summary=None,
    evidence="",
    options=(),
    interrupt="brief",
    producer=None,
    expires_hours=None,
    tags=(),
):
    """Post one judgement request; returns its card id immediately.

    Evidence discipline: a card whose answer destroys or publishes something
    leads with what is destroyed and what is unique about it — reassurance
    about things not at risk is persuasion, not briefing. State facts as of
    now, and prefer the service's short default expiry: a question worth days
    of waiting is worth re-asking with fresh evidence.
    """
    payload = {
        "title": title,
        "summary": summary or title,
        "evidence": evidence,
        "options": list(options),
        "interrupt": interrupt,
        "producer": producer
        or os.environ.get(
            "MDJUDGE_PRODUCER",
            f"{os.environ.get('USER', 'agent')}@{socket.gethostname()}",
        ),
        "tags": list(tags),
    }
    if expires_hours is not None:
        payload["expires"] = (
            datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        ).isoformat(timespec="seconds")
    return _call("POST", "request", payload)["id"]


def resolve(request_id):
    """The verdict so far: status, answer, and the pinned bytes once answered."""
    return _call("GET", f"request/{request_id}")


def wait(request_id, *, poll=20, timeout=None):
    """Block until answered; return the answer.

    Raises `Expired` when the request lapses and `TimeoutError` on the
    caller's own deadline (the request stays open — resolve it later).
    The answer authorizes the act described on the card: if time has passed,
    re-verify the world before acting.
    """
    deadline = time.monotonic() + timeout if timeout else None
    while True:
        verdict = resolve(request_id)
        if verdict["status"] == "answered":
            return verdict["answer"]
        if verdict["status"] != "open":
            raise Expired(f"{request_id}: {verdict['status']} without an answer")
        if deadline and time.monotonic() > deadline:
            raise TimeoutError(f"{request_id} still open; resolve it later")
        time.sleep(poll)
