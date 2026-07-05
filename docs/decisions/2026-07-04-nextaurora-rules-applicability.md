# ADR: Which NextAurora conventions apply to riparian-poc

**Date:** 2026-07-04
**Status:** Accepted
**Owner:** Joshua Dell (solo)

## Context

We ported the **NextAurora encoding-loop method** (review surfaces, mechanical gates, lean
canon) into this repo. NextAurora is a **DDD / Vertical-Slice e-commerce microservices**
system (EF Core, Wolverine messaging, sagas, aggregates, gRPC). Riparian-poc is a
**geospatial ETL + read-mostly GeoJSON API + Python ML pipeline** (Dapper, PostGIS, batch
ETL, no messaging).

Porting the *method* is right. Porting NextAurora's *architecture* would be cargo-culting.
This ADR records — explicitly — which of NextAurora's rules apply, so a future reviewer
knows the divergences were **conscious decisions, not drift**.

## Decision

Adopt NextAurora's **architecture-agnostic** standards + the method; do **not** adopt its
**DDD/VSA/microservices** patterns.

### Adopted (retuned into CLAUDE.md, the architecture-reviewer, and .coderabbit.yaml)
- SOLID; small ISP interfaces; `async`/`CancellationToken`; `sealed`, file-scoped
  namespaces, records; structured `ILogger<T>` templates.
- **Service → repository → thin endpoint** layering; `TypedResults`; OpenTelemetry spans.
- Dapper conventions (`CommandDefinition`, `MatchNamesWithUnderscores`, `ST_AsGeoJSON`).
- Medallion one-way (bronze → silver → gold); additive `*_migration.sql`; parameterized SQL.
- Python: `Protocol` DI, type hints, frozen dataclasses, pure-function separation.
- The encoding loop itself (5 surfaces × 3 tiers, mechanical gates).

### Deliberately NOT adopted (inapplicable to this system)
- **Repositories: KEPT (the notable divergence).** NextAurora *removed* `IFooRepository`
  because with EF Core `DbContext` **is** the Unit-of-Work and `DbSet<T>` **is** the
  Repository — the wrapper is redundant. Riparian uses **Dapper**, a raw query executor that
  is *not* a UoW/repository. So `IPostGisRepository` is a **genuine SRP abstraction** (it owns
  GeoJSON `FeatureCollection` building, MVT aggregation, typed mapping, connection lifetime,
  and `NpgsqlException` handling — none of which belong in a service) and it passes
  NextAurora's own "interfaces earn their keep" test via the **test-mock** justification (it
  is the seam that lets services be unit-tested without a database). **Keep it. Do not
  "simplify" it away — the EF reasoning does not transfer to Dapper.**
- **VSA feature slices** → riparian's API is service-layer; `/new-feature-slice` was replaced
  with `/add-endpoint`, `/add-etl-step`, `/add-map-layer`.
- **CQRS Command/Query naming** → read-mostly GeoJSON API, no command bus.
- **DDD aggregates, factory methods, `Guid.CreateVersion7()`, optimistic-concurrency tokens**
  → no write-heavy domain aggregates.
- **Wolverine handlers, outbox atomicity, saga steps** → not a messaging system.
- **IDOR predicates, JWT/auth model** → open-CORS dev API, no per-user scoping (revisit for
  production).
- **gRPC contracts** → no inter-service comms.

## Consequences

- The `architecture-reviewer` agent + `.coderabbit.yaml` are tuned to riparian's **actual**
  architecture (service-layer + Dapper + medallion + Python-ETL), not NextAurora's DDD/VSA.
- Contributors should **not** flag `IPostGisRepository` as a redundant wrapper (it isn't —
  see above), and should **not** impose VSA/CQRS/aggregate patterns.
- If riparian ever adds write-heavy domain logic, auth, or inter-service messaging, revisit
  the "not adopted" list.
