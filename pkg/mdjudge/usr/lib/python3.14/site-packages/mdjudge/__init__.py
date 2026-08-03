"""Judgement requests over mddb: request, answer, and the availability queue.

A judgement card asks a human one question with bounded evidence and records
one answer. The request stratum is written once by `request_card` and never
mutated; the answered stratum is written once by `answer_card`, stamping the
deck sha whose bytes the answerer read (`mddb.MDDB.at` resolves them later).
The gate — who may call answer_card, behind which credential — is tenancy
wiring, deliberately outside this library.
"""

from mdjudge._core import (
    INTERRUPTS,
    STATUSES,
    AlreadyAnswered,
    answer_card,
    open_requests,
    request_card,
)

__version__ = "0.0.1"
__all__ = [
    "INTERRUPTS",
    "STATUSES",
    "AlreadyAnswered",
    "answer_card",
    "open_requests",
    "request_card",
]
