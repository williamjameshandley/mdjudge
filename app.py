"""HTTP entrypoint for mdjudge: the judgement queue PWA and its API.

Serves the static shell and the ``/judge/api/...`` API over the one mddb deck
at ``$DECK``, on the AF_UNIX socket ``$SOCKET`` (the nginx front door proxies
``/judge/`` to it). Producers POST requests; the surface GETs the queue and
POSTs answers. Every queue payload carries the deck sha captured before the
payload was derived; an answer threads it back and it is stamped as
``approved_sha`` — the audit of which bytes the human read.

Development posture: the API is open on the intranet. The answer credential
(mdgtd-style bearer provisioned by init, QR-delivered) lands when this
hardens; nothing else about the wire contract changes.

Every request opens a fresh ``mddb.MDDB`` handle: mddb self-heals a stale
cache only at open, and producers may commit from other processes.
"""

import os
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from socket import AF_UNIX

import mddb
import mdjudge
from alan_pwa.server import BaseHandler, ValidationError

DECK = os.environ["DECK"]
SOCKET = os.environ["SOCKET"]

DEFAULT_TTL = timedelta(hours=8)
"""Requests without an explicit expiry lapse after a working day: an unanswered
question is stale evidence, and the producer must re-ask, not trust a yes to a
day-old context."""


def _now():
    return datetime.now(timezone.utc)


def queue(availability):
    db = mddb.MDDB(DECK)
    sha = db.head()
    cards = []
    ages = dict(db.conn.execute("SELECT id, first_commit FROM entries"))
    for card_id in mdjudge.open_requests(db, availability, now=_now()):
        card = db.read(card_id)
        cards.append(
            {
                "id": card.id,
                "asked": ages[card.id],
                "title": card.title,
                "summary": card.summary,
                "options": card.yaml.get("options", []),
                "interrupt": card.yaml["interrupt"],
                "expires": card.yaml.get("expires"),
                "producer": card.yaml["producer"],
                "tags": card.yaml.get("tags", []),
                "body": card.body,
            }
        )
    return {"sha": sha, "requests": cards}


def create_request(req):
    for key in ("title", "summary", "producer"):
        if not isinstance(req.get(key), str) or not req[key]:
            raise ValidationError(f"{key} must be a non-empty string")
    interrupt = req.get("interrupt", "brief")
    if interrupt not in mdjudge.INTERRUPTS:
        raise ValidationError(f"interrupt must be one of {mdjudge.INTERRUPTS}")
    options = req.get("options", [])
    if not isinstance(options, list):
        raise ValidationError("options must be a list")
    if "expires" in req:
        expires = datetime.fromisoformat(req["expires"])
        if expires.tzinfo is None:
            raise ValidationError("expires must be timezone-aware ISO 8601")
    else:
        expires = _now() + DEFAULT_TTL
    db = mddb.MDDB(DECK)
    with db.editor(rationale=f"request from {req['producer']}") as editor:
        card = mdjudge.request_card(
            editor,
            title=req["title"],
            summary=req["summary"],
            evidence=req.get("evidence", ""),
            producer=req["producer"],
            interrupt=interrupt,
            options=options,
            expires=expires,
            tags=req.get("tags", []),
        )
    return {"id": card.id, "sha": db.head()}


def answer_request(req):
    for key in ("id", "answer", "sha"):
        if not isinstance(req.get(key), str) or not req[key]:
            raise ValidationError(f"{key} must be a non-empty string")
    db = mddb.MDDB(DECK)
    with db.editor(rationale=f"answer {req['id'][:8]}") as editor:
        card = editor.read(req["id"])
        mdjudge.answer_card(
            editor,
            card,
            answer=req["answer"],
            approved_sha=req["sha"],
            surface=req.get("surface", "pwa"),
            now=_now(),
        )
    return {"id": req["id"], "answer": req["answer"], "sha": db.head()}


def resolve(card_id):
    """The producer's read: the card, and its bytes at the approved sha."""
    db = mddb.MDDB(DECK)
    card = db.read(card_id)
    payload = {
        "id": card.id,
        "status": card.yaml["judgement_status"],
        "answer": card.yaml.get("answer"),
        "answered_at": card.yaml.get("answered_at"),
        "answered_by": card.yaml.get("answered_by"),
    }
    if "approved_sha" in card.yaml:
        approved = db.at(card.id, card.yaml["approved_sha"])
        payload["approved_sha"] = card.yaml["approved_sha"]
        payload["approved_body"] = approved.body
    return payload


class Handler(BaseHandler):
    server_version = "mdjudge"
    static_dir = Path(os.environ.get("STATIC", "/usr/lib/mdjudge/static"))
    shell_paths = frozenset({"/judge", "/judge/"})
    shell_file = "app.html"
    static_map = {
        f"/judge/{name}": ctype
        for name, ctype in {
            "app.css": "text/css",
            "app.js": "application/javascript",
            "sw.js": "application/javascript",
            "manifest.json": "application/manifest+json",
            "icon-192.png": "image/png",
            "icon-512.png": "image/png",
        }.items()
    }
    kit_map = {
        "/judge/pwa.css": "text/css",
        "/judge/pwa-sw.js": "application/javascript",
        "/judge/toast.js": "application/javascript",
    }

    def _file(self, name, ctype):
        super()._file(name.removeprefix("judge/"), ctype)

    def _kit_file(self, name, ctype):
        super()._kit_file(name.removeprefix("judge/"), ctype)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if self._serve_static(path):
            return
        if path == "/judge/api/queue":
            query = dict(
                pair.split("=", 1)
                for pair in self.path.partition("?")[2].split("&")
                if "=" in pair
            )
            availability = query.get("availability", "open")
            if availability not in ("open", "brief", "silent"):
                self._send(400, b"bad availability", "text/plain")
                return
            self._json(200, queue(availability))
            return
        if path.startswith("/judge/api/request/"):
            self._boundary(lambda _: resolve(path.rsplit("/", 1)[1]), b"{}")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path == "/judge/api/request":
            self._boundary(create_request, self._body())
            return
        if self.path == "/judge/api/answer":
            try:
                self._boundary(answer_request, self._body())
            except mdjudge.AlreadyAnswered as error:
                self._send(409, f"already answered: {error}".encode(), "text/plain")
            return
        self._send(404, b"not found", "text/plain")


class UnixServer(ThreadingHTTPServer):
    address_family = AF_UNIX

    def server_bind(self):
        Path(self.server_address).unlink(missing_ok=True)
        self.socket.bind(self.server_address)
        os.chmod(self.server_address, 0o666)
        self.server_name, self.server_port = "mdjudge", 0


if __name__ == "__main__":
    server = UnixServer(SOCKET, Handler)
    print(f"mdjudge on {SOCKET}")
    server.serve_forever()
