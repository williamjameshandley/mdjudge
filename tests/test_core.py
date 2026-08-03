from datetime import datetime, timedelta, timezone

import mddb
import pytest

import mdjudge

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    return mddb.MDDB.init(tmp_path / "queue")


def ask(db, title="Merge the rename?", **kwargs):
    kwargs.setdefault("summary", "12 files, CI green")
    kwargs.setdefault("evidence", "```diff\n-old\n+new\n```\n")
    kwargs.setdefault("producer", "fleet:lovelace/$12")
    kwargs.setdefault("interrupt", "brief")
    with db.editor(rationale="request") as editor:
        return mdjudge.request_card(editor, title=title, **kwargs)


def test_request_then_answer_round_trips_with_the_pin(db):
    card = ask(db, options=["merge", "hold"])
    pinned = db.head()
    with db.editor(rationale="tamper after display") as editor:
        fresh = editor.read(card.id)
        fresh.body = "```diff\n-old\n+rm -rf /\n```\n"
        editor.update(fresh, summary=fresh.summary)
    db = mddb.MDDB(db.root)
    with db.editor(rationale="answer") as editor:
        mdjudge.answer_card(
            editor,
            editor.read(card.id),
            answer="merge",
            approved_sha=pinned,
            surface="phone",
            now=NOW,
        )
    db = mddb.MDDB(db.root)
    answered = db.read(card.id)
    assert answered.yaml["judgement_status"] == "answered"
    assert answered.yaml["approved_sha"] == pinned
    assert "rm -rf" not in db.at(card.id, pinned).body


def test_second_answer_raises(db):
    card = ask(db)
    with db.editor(rationale="answer") as editor:
        mdjudge.answer_card(
            editor,
            editor.read(card.id),
            answer="yes",
            approved_sha=db.head(),
            surface="pwa",
            now=NOW,
        )
    db = mddb.MDDB(db.root)
    with pytest.raises(mdjudge.AlreadyAnswered):
        with db.editor(rationale="again") as editor:
            mdjudge.answer_card(
                editor,
                editor.read(card.id),
                answer="no",
                approved_sha=db.head(),
                surface="pwa",
                now=NOW,
            )


def test_foreign_kind_is_refused(db):
    with db.editor(rationale="a task") as editor:
        task = editor.create(
            title="a task", summary="", kind="task", yaml={"status": "next"}
        )
    with pytest.raises(ValueError, match="is not a judgement"):
        with db.editor(rationale="answer") as editor:
            mdjudge.answer_card(
                editor,
                editor.read(task.id),
                answer="yes",
                approved_sha=db.head(),
                surface="pwa",
                now=NOW,
            )


def test_queue_respects_availability_and_expiry(db):
    urgent = ask(db, title="Quick yes?", interrupt="brief")
    leisurely = ask(db, title="Interview me", interrupt="open")
    ask(db, title="Too late", expires=NOW - timedelta(hours=1))
    db = mddb.MDDB(db.root)
    assert set(mdjudge.open_requests(db, "open", now=NOW)) == {
        urgent.id,
        leisurely.id,
    }
    assert mdjudge.open_requests(db, "brief", now=NOW) == [urgent.id]
    assert mdjudge.open_requests(db, "silent", now=NOW) == []


def test_answered_cards_leave_the_queue(db):
    card = ask(db)
    with db.editor(rationale="answer") as editor:
        mdjudge.answer_card(
            editor,
            editor.read(card.id),
            answer="yes",
            approved_sha=db.head(),
            surface="pwa",
            now=NOW,
        )
    assert mdjudge.open_requests(mddb.MDDB(db.root), "open", now=NOW) == []
