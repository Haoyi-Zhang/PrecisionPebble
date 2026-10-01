# Preparation-aware weighted pebbling

A self-contained research artifact for **Preparation-Aware Weighted Pebbling for Precision-Changing Operator Trees**. This directory is the root of the standalone `tight-pebbling-bounds-precision` repository. It does not require the manuscript directory, a private cache, an online account, a solver service, a model API, or a network connection.

## Implemented contract

The planner jointly chooses representations, operator recipes, spill edges, and execution order on a rooted unique-consumer in-tree. It exactly minimizes transferred allocation units, with nonnegative rational abstract work as a lexicographic tie-breaker, **only when every allowed recipe's output allocation is at most each operand's allocation**. Operators are pure, atomic, and non-overwriting. The capacity dependence is pseudo-polynomial. The configuration search is a separately implemented small-instance oracle; this is implementation separation, not independent authorship or blind review.

`proofs/core.md` contains the human-readable arguments for ancestry pruning, the spill-forest identity, component serialization, the exact recurrence, the tight `23t/25t` family, and the NP-complete expansive extension. The proofs are not mechanized. The recurrence in expansive mode is only a feasible upper-bound policy. The retained executable model has no separate hidden-workspace field: a front end must lower temporary storage to explicit values or allocations before applying this contract. No hardware, deployment, energy, floating-point-accuracy, or model-performance claim is supported.

JSON numerical fields are fail-closed. Capacities, allocations, representation labels, event states, and rational-cost numerators/denominators must be JSON integers; booleans and fractional numbers are rejected rather than truncated. Rational pairs such as `[1, 2]` remain exact `Fraction(1, 2)` values. The parser does **not** claim to detect duplicate object keys in raw JSON text.

## Checker responsibilities

The three executable checks have different contracts.

- `src/event_checker.py` replays one normalized, one-shot trace: a source is loaded at most once and an operator is computed at most once. This is the trace class justified by the paper's normalization lemmas, not an arbitrary recomputing pebble-game execution. The checker recomputes legality, capacity, peak allocation, transferred units, rational work, and the final stored root.
- `src/bellman_checker.py` recursively evaluates the recurrence into a fresh memo, derives the expected reachable key set and costs, and then compares that mapping with the supplied certificate. It does not trust a claimed external table-dependency order.
- `src/claim_checker.py` connects a claimed optimum to the actual event and certificate checks. The changed-optimum negative control passes a deliberately altered cost through this entry point and is rejected by both the recomputed trace cost and the recomputed certificate terminal cost.

The positive expansive-valley witness in `instances/witnesses/expansive-valley-33.json` was frozen from deterministic configuration-oracle predecessor reconstruction. It is then replayed by the event checker, which confirms I/O 33 and peak allocation 18. It is not described as a hand-authored trace or an independently produced research result.

## Requirements and clean reproduction

A Linux/POSIX environment with Python 3.10 or newer and its standard library is required. No package installation is needed. The runner uses one CPU worker, a 3 GiB address-space limit, and no GPU or network access. Run the following commands sequentially from this directory:

```sh
rm -rf results/replay
for step in 1 2 3 4 5 6; do
  python3 reproduce.py --output results/replay --chunk 64 || exit "$?"
done
python3 tools/check_controls.py --output results/replay-controls.json
python3 tools/check_reference_equation.py --output results/replay-reference-equation.json
python3 -m unittest discover -s tests -v
python3 tools/summarize.py --results results/replay --output results/replay-summary
python3 tools/compare_replay.py \
  --reference results/evaluation \
  --replay results/replay \
  --output results/replay-comparison.json
```

A fresh replay directory is required for a clean replay. Existing output is treated as recovery state, not silently overwritten. Every retained case record is bound to its frozen index position, name, group, input path, input SHA-256 digest, and evaluation configuration. The summary and comparison tools validate that identity against the frozen index; matching record counts alone are insufficient. Empty or nonexistent campaigns, identical reference/replay directories, missing records on both sides, stale inputs, and unexpected files are rejected.

The runner checks its caps at resume start, before submitting each case, after a candidate returns, and before emitting a complete manifest. A candidate that crosses a cap is persisted as `incomplete`; a later zero-work invocation cannot convert it to `complete`. The fixed limits are 600,000 **instrumented audit units**, 364 cases, and 2,700 cumulative **case-body process CPU seconds**. Per-oracle limits are 50,000 discovered states and 15 case CPU seconds.

The timing fields intentionally distinguish three quantities:

- `case_body_cpu_seconds`: process CPU measured inside `evaluate_case`; only this sum is compared with the 2,700-second campaign cap;
- `invocation_process_cpu_seconds`: process CPU for an entire `reproduce.py` invocation, including recovery checks and JSON I/O;
- external timing: elapsed time and process-tree resource measurements collected outside the runner.

## Instrumented audit units

`audit_units` is a transparent diagnostic sum, not an instruction count, a wall-clock predictor, or a conservative upper bound on every executed operation. For each case it adds exactly the retained counters for:

1. prepared-policy optimizer states;
2. prepared-policy certificate alternatives;
3. prepared event-replay steps;
4. contiguous-policy states and enumerated alternatives;
5. oracle expanded states and oracle event-replay steps;
6. typed semantic node evaluations;
7. fixed-64 optimizer states, event-replay steps, and semantic node evaluations.

The per-component values are stored in `metrics.audit_unit_components`, and `audit_units` must equal their sum. Startup, parsing, hashing, result serialization, priority-queue maintenance, and other uninstrumented operations are deliberately not represented by this mixed counter.

## Retained evidence

The frozen campaign contains 364 deterministic constructed instances: 256 structural-grid cases, 16 larger structural cases, eight analytic separation cases, four controls, two hardness controls, 24 scaling cases, and 54 exact-integer IR cases. They are not a sampled natural-workload benchmark. Observed maxima are 64 vertices, 117 recipes, capacity 1,024, and four representation labels `{8,16,32,64}`.

The repaired clean campaign and clean replay both contain:

- 364 checked cases;
- 286 complete configuration searches;
- 283 oracle agreements to which the contractive theorem applies;
- 361 checked Bellman certificates;
- 31,161 prepared-policy optimizer states;
- 69,035 Bellman alternatives;
- 60,065 discovered oracle states;
- 255,792 instrumented audit units.

All 54 integer-IR instances remain: 48 are feasible with typed choices, 36 at fixed 64 bits, 12 are typed-only, and six are infeasible in both. All 36 jointly feasible cases have lower I/O under typed planning than fixed-64 planning; **none** has lower I/O from preparation than from the typed-contiguous policy. That absence is a retained negative result.

The complete campaign uses 2.642924087 cumulative case-body CPU seconds and 3.231044784 cumulative invocation-process CPU seconds. The six external invocations total 9.08 process CPU seconds, 6.75 summed elapsed seconds, and 137,708 KiB maximum process-tree RSS on the retained host. These host-dependent values are not compared for logical replay equality.
The post-repair clean replay records 2.702529778 case-body CPU seconds, 3.301595159 invocation CPU seconds, 8.88 user plus 0.45 system CPU seconds externally, 6.96 seconds elapsed, and 137,748 KiB peak RSS. It retains 255,792 audit units and matches all 364 logical records; the timing/RSS changes are the only observed differences.

## Files and boundaries

- `src/`: model, exact planner, configuration oracle, event/claim/Bellman checkers, contiguous baseline, generators, exact-integer semantics, and campaign integrity utilities.
- `proofs/core.md`: general proofs and finite-check boundaries.
- `instances/`: exact frozen inputs and the fixed valley witness.
- `results/evaluation/`: retained clean campaign records and manifest.
- `results/summary/`: tables derived only after complete index-bound validation.
- `tests/`: model, checker, campaign-integrity, bibliography, and reference-equation fixtures.
- `tools/`: input construction, controls, summarization, replay comparison, and bibliography audit.

The reference-policy implementation transcribes the fixed-state recurrence from Bhattacharjee et al., SPAA 2025, DOI 10.1145/3694906.3743342; it is not their software and does not reproduce their devices or workloads. No external baseline internals were modified.

## Research provenance and external use

Substantive AI assistance was used in model and proof development, counterexamples, code, experimental design and execution, analysis, source comparison, and manuscript/figure writing. Artifact-only self-audits are not independent blind review. This is internal research, not an accepted or submitted article. Human authorship, accountability, current venue permission, AI-use disclosure, and submission declarations require truthful verification before external use. No repository URL is asserted.

The MIT license covers newly authored repository material. Third-party publications and tools retain their own licenses; see `external_resources.csv`.
