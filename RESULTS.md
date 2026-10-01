# Retained results

## Clean campaign and replay

The repaired evaluation contains 364 deterministic instances, all with status `checked`. The configuration oracle completes on 286 instances. Of these, 283 are allocation-contractive and agree with the preparation-aware recurrence; the other three are deliberately outside the exact theorem. The separately implemented Bellman checker validates 361 certificates, including infeasible tables.

A second clean directory reproduces all 364 logical records. `tools/compare_replay.py` first validates both campaigns against the frozen index, input digests, and evaluation configuration, and then compares all logical fields. It rejects nonexistent or empty directories, the same directory on both sides, common omissions, stale inputs, and same-count identity substitutions. The retained comparison has zero validation errors and zero logical mismatches.

## Audit counter and timing

The campaign records 255,792 **instrumented audit units**. This is the explicit sum of prepared optimizer states, certificate alternatives, prepared event steps, contiguous-policy states and alternatives, oracle expanded states and replay steps, typed semantic evaluations, and fixed-64 optimizer/event/semantic work. It is not a conservative bound on all instructions or all execution paths.

The retained totals include 31,161 prepared optimizer states, 69,035 Bellman alternatives, and 60,065 discovered oracle states. The campaign uses 2.642924087 cumulative case-body process CPU seconds, the quantity governed by the 2,700-second cap. Six invocations use 3.231044784 process CPU seconds inside the complete runner. External timing totals 9.08 process CPU seconds and 6.75 summed elapsed seconds, with 137,708 KiB maximum process-tree RSS. These timing and memory values are host-dependent.

The post-repair clean replay uses 2.702529778 case-body CPU seconds and 3.301595159 invocation CPU seconds. External timing of its six runner invocations is 8.88 user plus 0.45 system CPU seconds, 6.96 seconds elapsed, and 137,748 KiB peak RSS. The replay has the same 255,792 audit units and no logical mismatch; only host-dependent timing and RSS differ from the retained evaluation.

## Decisive cases

- The contractive ten-node control has unrestricted optimum 89 and whole-logical-subtree-contiguous cost 91. The analytic family scales as `23t` and `25t`.
- The noncontractive seven-node valley has unrestricted optimum 33, preparation-policy upper bound 35, and contiguous cost 49. The fixed trace in `instances/witnesses/expansive-valley-33.json` comes from oracle predecessor reconstruction; direct event replay confirms I/O 33 and peak 18.
- In the affine reduction controls, the yes instance reaches compulsory floor 2,440; the no instance has floor 3,904 and oracle optimum 3,920. These finite cases check the construction plumbing, not the general proof.

## Exact-integer IR

The 54 cases cover sums, dot products, and sums of absolute differences. Forty-eight are feasible with typed choices; 36 are feasible at fixed 64 bits; 12 are typed-only; six are infeasible in both modes. In every jointly feasible case, typed planning has lower I/O than fixed-64 planning. None has lower I/O under preparation than under the typed-contiguous policy. The 240 typed and 180 fixed-64 semantic-pattern checks pass.

The absence of preparation gains in this finite generated set is a retained negative result. These cases establish precision-dependent feasibility and transfer costs within the declared exact-integer contract, not natural-workload prevalence or hardware speedup.

## Coverage table

| Group | Cases | Max vertices | Complete oracles | Certificates | Audit units |
|---|---:|---:|---:|---:|---:|
| small | 256 | 5 | 256 | 256 | 10,744 |
| extended | 16 | 7 | 16 | 16 | 1,967 |
| separation | 8 | 10 | 8 | 8 | 2,728 |
| control | 4 | 12 | 4 | 3 | 2,258 |
| hardness | 2 | 14 | 2 | 0 | 42,114 |
| scaling | 24 | 64 | 0 | 24 | 93,000 |
| integer | 54 | 31 | 0 | 54 | 102,981 |
| **total** | **364** | **64** | **286** | **361** | **255,792** |

## Checker controls

Three valid objects are accepted: a valid Bellman certificate, a valid cost/trace/certificate claim, and the frozen oracle-reconstructed valley trace with I/O 33 and peak 18. Ten fixed corruptions or invalid requests are rejected.

The changed-claimed-optimum control no longer performs a stand-alone inequality comparison. It changes 89 to 90 and sends that claim through `check_solution_claim`; rejection records both the trace-recomputed cost 89 and the Bellman-recomputed terminal cost 89. Other controls alter a source state, capacity, final store, certificate cost or key set, theorem applicability, enumeration limit, and reference-policy input contract.

## Numeric and recovery fixtures

Small fixtures confirm that fractional capacities and allocations (`31.9`, `64.9`), fractional work numerators (`-0.5`), and booleans in integer fields are rejected rather than truncated; `[1,2]` is preserved exactly. Additional fixtures confirm that an over-budget final case is persisted as `incomplete`, a subsequent empty run remains incomplete, input changes invalidate recovery through their digest, and summary/comparison require frozen-index identity rather than record counts alone.

The universal theorems remain human-readable proofs in `proofs/core.md`; no test count or executable certificate is described as a mechanized proof.
