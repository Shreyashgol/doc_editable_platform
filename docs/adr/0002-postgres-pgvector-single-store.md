# ADR 0002 — PostgreSQL + pgvector as single system of record (with escape hatches)

- **Status:** Accepted
- **Date:** 2026-06-20

## Context
We need relational metadata, typed JSONB properties, vector similarity search, and a symbol
graph. The brief mandates pgvector and anticipates a future Neo4j migration and RAG.

## Decision
Use **PostgreSQL + pgvector** as the single store in v1: relational tables for documents/symbols,
JSONB for flexible properties, `vector(512)` + HNSW index for embeddings, and an adjacency-list +
recursive CTE for the graph. Hide vector search behind `SymbolRepository.search_similar` and the
graph behind `RelationshipRepository`, so each can migrate to a specialized engine independently.

## Consequences
- (+) One database to operate, transactionally consistent, simple local dev.
- (+) Cross-modal search works today via OpenCLIP text/image towers into one vector column.
- (+) Clear migration path: adapters, not rewrites (Qdrant/Milvus for vectors; Neo4j for graph).
- (−) Single store has a scaling ceiling for very large vector/graph workloads; accepted for v1
  and de-risked by the port boundaries.

## Alternatives
- **Dedicated vector DB + graph DB from day one:** more operational surface and cost before
  product validation. Deferred behind ports.
