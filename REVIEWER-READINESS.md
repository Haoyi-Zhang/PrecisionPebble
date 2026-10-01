# Reviewer-Readiness Notes

This file maps likely P2 validation and reproducibility questions to the current artifact. It does not claim external review or acceptance.

## Model and theorem boundary

The exact result is limited to pure unique-consumer in-trees, atomic non-overwriting operations, whole-value transfers, and recipe-wise allocation contraction. The executable model has no hidden workspace field: temporary storage must be lowered to explicit values or conservatively included in declared allocations. Expansion is outside the exact theorem; the 33/35/49 valley demonstrates that boundary without invalidating the contractive theorem.

## Checker contracts

- `event_checker` replays normalized one-shot traces justified by the paper's normalization lemmas. It is not a verifier for arbitrary recomputing executions.
- `bellman_checker` recursively recomputes a fresh memo, then compares the complete reachable key set and exact costs. It does not consume an externally verified dependency order.
- `claim_checker` checks a claimed optimum against both event and certificate recomputation. The 90-for-89 corruption is rejected through this actual entry point.
- Raw duplicate JSON keys are not a claimed validation feature.
- The positive valley trace is frozen from deterministic oracle predecessor reconstruction and replayed at I/O 33 and peak 18.

## Counters and timing

`audit_units` is the sum of named retained instrumentation components: prepared states and alternatives, event replay for prepared/contiguous/oracle/fixed-64 paths, oracle states, and typed/fixed-64 semantic node evaluations. It omits noninstrumented operations and is not a conservative full-run bound.

The 2,700-second limit applies to cumulative per-case body process CPU. Whole-invocation process CPU and external elapsed/process-tree measurements are separate fields. The retained evaluation records 2.642924087 case-body CPU seconds, 3.231044784 invocation CPU seconds, and 9.08 externally measured process CPU seconds.

## Recovery and comparison integrity

Frozen records bind index position, case identity, input digest, and evaluation configuration. Summary generation validates exact identity membership. Replay comparison rejects nonexistent/empty inputs, self-comparison, common omissions, and identity substitutions. Budget gates run at recovery, before submission, after a candidate, and before completion. An over-budget candidate remains persistently incomplete.

## Input validation

Integer fields reject floats and booleans before conversion. Tests cover `31.9`, `64.9`, `[-0.5,1]`, and Boolean contamination; `[1,2]` remains exact. These are executed regression results, not merely static concerns.

## Evidence and limits

The clean evaluation and replay each contain 364 cases, 286 complete configuration searches, 283 applicable agreements, 361 certificates, and integer feasibility counts 48/36. The two logical result sets match exactly. The finite evidence is constructed coverage, not a natural workload sample. The proof is not mechanized, the implementations are separated rather than independently authored, and no hardware, performance, or acceptance claim is made.
