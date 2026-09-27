# ADR 0051: Rumination defaults to disabled

**Status:** Accepted
**Date:** 2026-09-27

## Context

Every prior write path in ROOTMEM only ever runs because some caller asked for it — an existing deployment upgrading to a new phase has never had its stored data change shape or content on its own. Rumination is the first mechanism that can rewrite existing relations (superseding one side of a contest) with nobody having asked, purely because time passed.

## Decision

`RUMINATION_ENABLED` defaults to `false`. An operator must explicitly opt in after upgrading, understanding that doing so lets the server autonomously resolve some contested relations going forward.

## Alternatives considered

- Defaulting to enabled, since the mechanism is safe (never destructive, always soft-supersede, fully audited): rejected — "safe" is not the same as "expected." An operator who upgrades and later notices relations changed with no corresponding request in any log they thought to check for should never have to first discover this feature exists that way.

## Consequences

A fresh deployment or CI environment sees no autonomous behavior unless it turns this on, keeping every existing test and integration unaffected by default. `docs/operations.md` documents what enabling it means in practice before recommending it.
