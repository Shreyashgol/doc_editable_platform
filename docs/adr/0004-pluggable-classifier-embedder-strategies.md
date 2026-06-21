# ADR 0004 — Pluggable classification & embedding strategies

- **Status:** Accepted
- **Date:** 2026-06-20

## Context
Classification must evolve through three phases — (1) deterministic rule engine
(`XV→Valve`, `PT→Pressure Transmitter`, …), (2) trained ML classifier, (3) Vision Transformer —
without re-architecting. Embeddings (OpenCLIP now) may later be fine-tuned or replaced.

## Decision
Define `SymbolClassifier` and `Embedder` **ports** in the domain. Ship v1 adapters
(`RuleBasedClassifier`, `OpenClipEmbedder`). The classify/embed worker stages depend only on the
port; the concrete strategy is chosen by configuration/DI. Classification results carry
`{method, raw_class, confidence}` so provenance is recorded and strategies can be A/B compared.

## Consequences
- (+) ML and ViT classifiers drop in as new adapters; no change to pipeline or domain.
- (+) Confidence + method stored → human-in-the-loop review and model comparison.
- (−) Rule engine has lower recall on unseen symbols in v1; mitigated by the editing UI and the
  clean upgrade path.

## Alternatives
- **Hard-code the rule engine in the worker:** blocks phases 2–3. Rejected.
