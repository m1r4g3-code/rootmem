# Phase 8 Research Memo — Background Rumination (Contested-Relation Reconciliation)

**Question this phase answers:** every mechanism ROOTMEM has ever had — search, consolidation, even Phase 7's auto-recall/auto-capture — runs only in reaction to something external: a tool call, a prompt, a turn ending. Nothing in the system has ever done anything on its own initiative, on its own schedule, with nobody asking. The user named this directly as the deeper, harder half of "closer to consciousness" (the other half, automatic invocation, shipped in Phase 7): something that "wakes up on its own... revisits contested or low-confidence memories... reprocesses without being asked."

## What already exists that this phase can reuse

- **Contested relations already exist and are already reachable.** `extraction/contradiction.py`'s `resolve_contradiction` (Phase 2, ADR 0013) marks both sides of an unresolved contradiction with `metadata.contested = true`, and neither is superseded — this is a real, already-produced state sitting in the graph today, with nothing that ever revisits it. `RelationRecord.is_contested` already exists as a property; no repository method lists contested relations yet.
- **The decay/retention math already exists and is directly reusable.** `retrieval/decay.py`'s `retention(now, last_accessed_at, created_at, access_count, salience, params)` (Phase 4, ADR 0023) computes `exp(-elapsed_days / stability_days(...))` from nothing but elapsed time — relations have no access-tracking, but they do have `recorded_at` (transaction time), which is exactly the `created_at` input this function already accepts with `last_accessed_at=None, access_count=0, salience=None`. No new decay model is needed; the existing one, applied to a different aggregate, already answers "how much should an unrefreshed belief have faded by now."
- **The Bayesian belief comparison already exists.** `belief_confidence(alpha, beta)` and the `supersede_margin` comparison in `resolve_contradiction` are the exact shape of decision rumination needs to make about a contested pair — the only change is comparing *decay-adjusted* confidence instead of raw confidence, since raw confidence never changes without new evidence and would never resolve anything on its own.
- **The audit trail, the inline-background-task pattern (Phase 2's `_maybe_consolidate`/`background_tasks` set with a `done_callback`), and the HTTP-mode-only server lifecycle (`main_async`) are all directly reusable** — this phase adds one more concurrent task to a process that already runs one indefinitely in HTTP mode, not a new kind of process.

## What genuinely doesn't exist yet, and is this phase's real new work

1. **Something that runs on a wall-clock timer, independent of any request.** Every prior "background" task in this codebase (the consolidation auto-trigger, the extraction providers' lazy construction) still only *starts* in reaction to a tool call. This phase's core new mechanism is a loop that starts once, at server startup, and keeps running on its own schedule for as long as the server process lives — the first genuinely autonomous process in this codebase.
2. **A decision rule for what "reconciling" a contest actually means**, worked out below.
3. **A way to discover contested pairs without a caller telling you which namespace to look in** — every existing repository method is namespace-scoped, because every existing caller is a namespace-scoped, authenticated request. A background process serving the whole deployment has no such caller.

## The reconciliation rule

Given a contested pair `(old, new)` — `old.recorded_at < new.recorded_at`, both `metadata.contested = true`, both still active (`valid_to IS NULL`) — define each side's **decayed confidence**:

```
decayed(r, now) = belief_confidence(r.belief_alpha, r.belief_beta) * retention(now, None, r.recorded_at, 0, None, params)
```

using the *same* `RetentionParams`/`decay_base_stability_days` setting Phase 4 already uses for memories — one decay model, reused for a second aggregate, not a parallel one invented for relations. Then reuse the *same* `supersede_margin` comparison `resolve_contradiction` already uses:

- if `decayed(new) > decayed(old) + margin`: **new wins** — `old` is superseded as of now (`valid_to`, `superseded_by` set; `contested` cleared on both).
- if `decayed(old) > decayed(new) + margin`: **old wins** — `new` is retroactively superseded as of now instead (bi-temporally legitimate: `valid_to`/`superseded_by` describe which belief is authoritative going forward, not which row is chronologically newer).
- otherwise: **still contested**, no change — most passes over most contests should find nothing to do yet, and that's the expected, common case, not a bug.

Because `old` always has at least as much elapsed time as `new` (it was recorded first), decay shrinks `old`'s confidence at least as much as `new`'s — meaning **an untouched contest trends toward resolving in favor of the newer side purely with the passage of time**, unless the older side's original belief was strong enough that decay hasn't caught up yet. This is a deliberate, honest simplification: preferring fresher, unrefreshed information over older, unrefreshed information when nothing else distinguishes them is a defensible default (it mirrors ordinary epistemic practice — "prefer the more recent report absent other evidence"), not a claim that it is the *correct* resolution in every case. Named explicitly as provisional, with a concrete revisit trigger: real usage might show contests should sometimes resolve toward the *better-established* older fact instead, which would require access-tracking on relations (not built here) the way memories already have it.

## Discovering contested pairs without a namespace

The background loop is server-side, trusted infrastructure — the same trust level as the `set_updated_at()` trigger or the audit-chain trigger, not a tenant-facing API call — so it queries `relations` directly for every row with `metadata.contested = true` (cross-namespace), groups by `(namespace, subject_entity_id, predicate)` in Python to reconstruct pairs, and reconciles each. The **explicit** `ruminate` MCP tool, by contrast, stays namespace-scoped and goes through the same `guarded`/`authorize_namespace` wrapper every other tool does — only the autonomous loop operates without a caller-supplied namespace. Three or more active contested rows sharing a key (a second contradiction arriving before the first is resolved) is a named, accepted limitation for this phase — handled defensively (compare pairwise, leave anything left over contested) rather than solved generally.

## What this phase deliberately does not attempt

**Cross-batch retrospective clustering** — re-examining episodic memories that were each individually consolidated (or never met a batch threshold) to find connections a single batch's narrower view couldn't see — was seriously considered as the rumination target instead of, or alongside, contested-relation reconciliation. It's a real, valuable idea (it directly answers the "session-trace batch scoping" limitation carried forward since Phase 2/3's retros), but it needs new clustering logic across an unbounded historical corpus, with real performance and cost questions this memo hasn't resolved. Rejected for this phase specifically to keep rumination's real novelty — a genuinely autonomous, self-scheduling process — from being entangled with a second, independently hard problem. Named as the concrete Phase 9+ candidate.

A learned/tunable decay-stability parameter specific to relations (as opposed to reusing memories' own `decay_base_stability_days`), access-tracking for relations, and any UI/dashboard surface for contested-relation history are all out of scope, unchanged from every prior phase's minimalism discipline.
