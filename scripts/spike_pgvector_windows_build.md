# Phase 1 Prototype-stage spike: native-Windows pgvector build

**Question:** can this specific Windows dev machine get a real, working `vector` extension without Docker, now that Phase 1 makes pgvector a hard requirement (no more Phase 0-style graceful skip)?

## What the build actually requires (per pgvector's own documented Windows process)

pgvector officially supports a Windows build via Visual Studio's `nmake`, not source compilation with a generic C compiler:

1. Visual Studio (Community edition is sufficient) with the **"Desktop development with C++"** workload installed.
2. Open an **x64 Native Tools Command Prompt for VS** (not a regular terminal — `vcvars64.bat` must be sourced first).
3. `set PGROOT=C:\Program Files\PostgreSQL\17`
4. `git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git`
5. `nmake /F Makefile.win` then `nmake /F Makefile.win install`

Sources: [pgvector4windows installation guide](https://github.com/ranga-NSL/pgvector4windows/blob/main/pgvector_installation_guide.md), [Mehmet Akar's Windows install writeup](https://mehmetakar.dev/install-pgvector-on-windows/), [pgvector/setup-pgvector](https://github.com/pgvector/setup-pgvector).

## Finding on this machine

Checked for the required toolchain: `cl.exe`, `nmake.exe`, and `vswhere.exe` (the standard way to detect any Visual Studio install) — **none are present**. No Visual Studio or standalone C++ Build Tools installation exists on this machine at all. Getting a working build here would first require installing the "Desktop development with C++" workload, which is itself a multi-gigabyte download and a non-trivial install step, before `nmake` could even be attempted.

## This is a genuinely different risk class than the WSL2/Docker failure

The Docker/WSL2 `CreateVm` timeout that blocked Phase 0 had **no known, documented resolution reachable from inside a session** — it pointed at BIOS/hypervisor/corporate-IT territory outside this session's control. The pgvector Windows build, by contrast, is a **fully documented, officially supported process** with a known, bounded cost (install one well-known toolchain, run two `nmake` commands). It is not blocked — it has simply not been attempted, because the toolchain isn't installed and installing it is a meaningfully sized, out-of-band step that a timeboxed spike shouldn't silently absorb without the user's sign-off (multi-GB download, meaningful install time, changes to the machine beyond this project's own footprint).

## Recommendation (see ADR 0011)

Two real options, not a forced choice made unilaterally by this spike:

1. **Install the Visual Studio C++ Build Tools workload and build pgvector natively.** Gets a fully native, no-new-service local dev setup, consistent with everything else Phase 0 already does natively. Cost: a real, if bounded, machine-level install this session shouldn't do without confirming first.
2. **Use a hosted Postgres with pgvector pre-enabled (e.g. Neon, Supabase free tier) for local dev only.** Zero local install, pgvector works immediately, no Windows-specific risk at all. Cost: local dev now depends on a network connection and an external account; CI and production are entirely unaffected either way since GitHub Actions' `ubuntu-latest` runners already use the official `pgvector/pgvector` Docker image with zero issues.

**CI and production are unaffected by this decision regardless of which option is chosen** — this is purely a local-inner-loop question for this one developer's machine, exactly as ADR 0006 already established for the graph-store decision.
