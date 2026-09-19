"""A small, hand-labeled retrieval set for `rootmem.evaluation.run` (ADR 0039).

**Synthetic and small, on purpose stated up front.** It is a fictional
platform team's memory: 30 memories and 15 queries, written by hand. Some
queries are pure semantic lookups where no extra signal should matter; others
are built so that recency, source trust or an explicit entity is the thing
that separates the right answer from a plausible wrong one. The set therefore
encodes an assumption -- that those signals often matter in real agent memory
-- and can show whether the Phase 4 ranking exploits them when they do. It
cannot show how often they matter in real usage, and with 15 queries it
supports direction, not significance.

Ages and access histories are relative to a fixed evaluation instant, so runs
are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalMemory:
    id: str
    content: str
    source: str  # "team-wiki" (trusted), "chat" (ordinary), "rumor" (weak)
    age_days: int
    access_count: int = 0
    salience: float | None = None
    entity: tuple[str, str] | None = None  # (entity_type, name) it is linked to


@dataclass(frozen=True)
class EvalQuery:
    id: str
    text: str
    relevance: dict[str, int]  # memory id -> graded relevance (0 absent)
    kind: str  # "semantic" | "freshness" | "trust" | "entity"
    entity: tuple[str, str] | None = None  # explicit entity signal, if the caller gives one


TRUST_BY_SOURCE: dict[str, float] = {"team-wiki": 0.95, "chat": 0.6, "rumor": 0.2}

MEMORIES: tuple[EvalMemory, ...] = (
    # --- plain facts: one clear answer each ---
    EvalMemory(
        "m01",
        "Production deploys are allowed Tuesday and Thursday between 10:00 and 15:00 UTC.",
        "team-wiki",
        30,
        1,
    ),
    EvalMemory(
        "m02", "The primary on-call engineer rotates every Monday at 09:00 UTC.", "team-wiki", 30, 1
    ),
    EvalMemory(
        "m03",
        "Database backups run nightly at 02:00 UTC and are retained for 35 days.",
        "team-wiki",
        45,
        1,
    ),
    EvalMemory(
        "m04",
        "Feature flags are managed in the LaunchPad dashboard; ask platform to create new ones.",
        "team-wiki",
        60,
        1,
    ),
    EvalMemory(
        "m05",
        "The staging environment is rebuilt from scratch every Sunday night.",
        "team-wiki",
        50,
    ),
    EvalMemory(
        "m06",
        "Customer data exports must be approved by the security lead before they are sent.",
        "team-wiki",
        70,
    ),
    EvalMemory(
        "m07",
        "Our vendor for transactional email is Postmark; the account owner is Dana Ortiz.",
        "chat",
        40,
    ),
    EvalMemory(
        "m08",
        "Expense reports are due by the fifth working day of the following month.",
        "team-wiki",
        80,
    ),
    EvalMemory(
        "m09",
        "The VPN uses hardware keys; lost keys must be reported to IT within one hour.",
        "team-wiki",
        55,
        1,
    ),
    EvalMemory(
        "m10",
        "Load tests must be scheduled in the shared calendar at least two days ahead.",
        "chat",
        35,
    ),
    # --- freshness conflicts: an old value and its newer replacement ---
    EvalMemory("m11", "The release freeze starts on the 15th of every month.", "chat", 200),
    EvalMemory(
        "m12", "The release freeze now starts on the 20th of every month.", "team-wiki", 10, 4, 0.7
    ),
    EvalMemory("m13", "Standup is at 09:30 in the Redwood room.", "chat", 300),
    EvalMemory("m14", "Standup moved to 10:00 on video call only.", "chat", 20, 6, 0.5),
    EvalMemory("m15", "The staging database password rotates quarterly.", "chat", 250),
    EvalMemory(
        "m16",
        "The staging database password now rotates monthly via the secrets manager.",
        "team-wiki",
        15,
        3,
        0.6,
    ),
    EvalMemory("m17", "Support tickets are answered within 48 hours.", "chat", 400),
    EvalMemory(
        "m18",
        "Support tickets are answered within 24 hours for paid plans.",
        "team-wiki",
        30,
        5,
        0.6,
    ),
    # --- trust conflicts: an authoritative source against a rumor ---
    EvalMemory(
        "m19",
        "The disaster recovery drill happens every six months and last ran in March.",
        "team-wiki",
        60,
        2,
    ),
    EvalMemory("m20", "I heard the disaster recovery drill was cancelled for good.", "rumor", 55),
    EvalMemory(
        "m21",
        "Employees get 25 days of paid leave per year, plus public holidays.",
        "team-wiki",
        90,
        2,
    ),
    EvalMemory("m22", "Someone said paid leave was cut to 20 days this year.", "rumor", 80),
    EvalMemory(
        "m23",
        "The production database runs PostgreSQL 16 with pgvector enabled.",
        "team-wiki",
        45,
        3,
    ),
    EvalMemory("m24", "Pretty sure we're moving the database to MongoDB soon.", "rumor", 40),
    # --- entity-linked memories ---
    EvalMemory(
        "m25",
        "Project Atlas ships its first beta to customers in the fourth quarter.",
        "team-wiki",
        20,
        2,
        0.6,
        ("project", "Project Atlas"),
    ),
    EvalMemory(
        "m26",
        "Atlas depends on the new billing service being ready first.",
        "chat",
        25,
        0,
        None,
        ("project", "Project Atlas"),
    ),
    EvalMemory(
        "m27",
        "The kickoff meeting notes for the mobile app redesign are in the shared drive.",
        "team-wiki",
        20,
    ),
    EvalMemory(
        "m28",
        "Project Borealis is the internal analytics dashboard rebuild.",
        "team-wiki",
        30,
        1,
        None,
        ("project", "Project Borealis"),
    ),
    EvalMemory(
        "m29",
        "Borealis will reuse the same data warehouse as Atlas.",
        "chat",
        30,
        0,
        None,
        ("project", "Project Borealis"),
    ),
    EvalMemory("m30", "The office plants are watered on Fridays.", "chat", 100),
)

QUERIES: tuple[EvalQuery, ...] = (
    # semantic: the wording shares few words with the answer
    EvalQuery("q01", "when can we ship code to production", {"m01": 3}, "semantic"),
    EvalQuery("q02", "who is on call this week", {"m02": 3}, "semantic"),
    EvalQuery("q03", "how long do we keep database backups", {"m03": 3}, "semantic"),
    EvalQuery("q04", "where do I turn a feature on or off for some users", {"m04": 3}, "semantic"),
    EvalQuery("q05", "what do I do if I lose my security key", {"m09": 3}, "semantic"),
    EvalQuery("q06", "who do we use to send automated emails to customers", {"m07": 3}, "semantic"),
    # freshness: the stale wording is just as close to the query
    EvalQuery("q07", "when does the release freeze begin", {"m12": 3}, "freshness"),
    EvalQuery("q08", "what time is the daily standup", {"m14": 3}, "freshness"),
    EvalQuery(
        "q09", "how often does the staging database password change", {"m16": 3}, "freshness"
    ),
    EvalQuery("q10", "how fast do we reply to support tickets", {"m18": 3}, "freshness"),
    # trust: an authoritative fact against a contradicting rumor
    EvalQuery("q11", "is the disaster recovery drill still happening", {"m19": 3}, "trust"),
    EvalQuery("q12", "how much paid leave do employees get", {"m21": 3}, "trust"),
    EvalQuery("q13", "what database do we run in production", {"m23": 3}, "trust"),
    # entity: the caller names the entity it is asking about
    EvalQuery(
        "q14",
        "when will Atlas launch",
        {"m25": 3, "m26": 1},
        "entity",
        ("project", "Project Atlas"),
    ),
    EvalQuery(
        "q15",
        "what is Borealis",
        {"m28": 3, "m29": 1},
        "entity",
        ("project", "Project Borealis"),
    ),
)
