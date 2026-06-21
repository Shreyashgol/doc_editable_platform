# ADR 0001 — Clean Architecture + DDD with explicit ports

- **Status:** Accepted
- **Date:** 2026-06-20

## Context
The platform must remain maintainable for years and absorb major capability swaps
(better classifiers, specialized vector/graph stores, new delivery protocols, RAG) without
rewrites. Business rules (symbol identity, state machine, label association) must be testable
in isolation and free of framework concerns.

## Decision
Adopt Clean Architecture with four layers (`domain`, `application`, `infrastructure`,
`interfaces`) plus `core`. The **domain** depends on nothing and defines **ports** (interfaces)
for every external capability. The **infrastructure** layer provides adapters. Wiring happens at
a single composition root (DI container). Source dependencies point inward only.

## Consequences
- (+) Domain is 100% unit-testable; ≥90% coverage is achievable.
- (+) Swapping OCR/embedder/classifier/graph-store = one adapter, zero domain change.
- (+) Delivery (REST → gRPC/GraphQL) is replaceable.
- (−) More files and indirection than a CRUD app; team must respect the dependency rule.

## Alternatives
- **2-layer CRUD (routes + ORM):** faster initially, but business logic leaks into routes and
  ORM, making the mandated swaps (Neo4j, ViT, vector DB) destructive. Rejected.
