# Retained results

## Campaign summary

The frozen evaluation contains 364 deterministic instances. All 364 records have status `checked`. The configuration oracle completed on 286 instances. Among them, 283 are allocation-contractive and agree with the preparation-aware recurrence; the remaining three are deliberately outside the exact theorem. The independent Bellman checker validated 361 certificates, including infeasible tables. The campaign charged 166,841 conservative enumeration units: 31,161 optimizer states, 69,035 checked Bellman alternatives and 60,065 oracle states.

Observed maxima were 64 vertices, 117 recipes, capacity 1,024, 3,004 optimizer states in one table, and 26,173 discovered oracle states. The six retained invocations accumulated 4.250585982 process CPU-seconds inside the runner; an outer measurement reported 18.56 user seconds, 1.48 system seconds, 14.82 seconds elapsed and 113,316 KiB maximum RSS. Timing and RSS are environment-dependent and are not compared bit-for-bit in replay.

## Decisive instances

- The contractive ten-node control has unrestricted optimum 89 and best whole-logical-subtree-contiguous cost 91. The parametric family scales these values as `23t` and `25t`.
- The noncontractive seven-node valley has unrestricted optimum 33, preparation-policy upper bound 35 and contiguous cost 49. It is a counterexample to extending the exchange lemma beyond contraction.
- In the affine reduction controls, the yes instance reaches its compulsory floor (2,440); the no instance has floor 3,904 but oracle optimum 3,920. These finite cases validate the construction plumbing, not the general NP-completeness proof.

## Exact-integer IR

The 54 retained cases cover sums, dot products and sums of absolute differences. Forty-eight are feasible with typed choices; 36 are feasible at fixed 64 bits; 12 are typed-only; six are infeasible in both modes. In every one of the 36 jointly feasible cases, typed planning has lower I/O than fixed 64-bit planning. None has lower I/O under preparation than under the contiguous typed policy. The 240 typed and 180 fixed-64 semantic-pattern checks all pass.

The absence of preparation gains in this finite integer set is a retained negative result. It prevents interpreting the designed 89/91 family as evidence that early preparation is common in practical workloads.

## Coverage table

| Group | Cases | Max vertices | Complete oracles | Certificates | Charged units |
|---|---:|---:|---:|---:|---:|
| small | 256 | 5 | 256 | 256 | 7,332 |
| extended | 16 | 7 | 16 | 16 | 1,442 |
| separation | 8 | 10 | 8 | 8 | 2,336 |
| control | 4 | 12 | 4 | 3 | 3,413 |
| hardness | 2 | 14 | 2 | 0 | 51,643 |
| scaling | 24 | 64 | 0 | 24 | 47,200 |
| integer | 54 | 31 | 0 | 54 | 53,475 |

## Checker controls

Two valid objects are accepted. Ten fixed corruptions or invalid requests are rejected: changed source representation, lowered capacity, removed terminal store, changed claimed optimum, corrupted table cost, removed table dependency, unexpected table state, exact-mode expansion, a deliberately tiny enumeration cap, and a typed input supplied to the fixed-state reference evaluator. A clean-room evaluator of the published fixed-weight Eq. (6), with the Eq. (7) root store, also returns 91 on the concrete separation and 25t on four parameter scales while the unrestricted witnesses cost 89 and 23t. These tests show that the checkers detect the named faults and that the reported recurrence comparison is reproducible; they are not a completeness proof for all implementation errors.

## Reproduction boundary

`results/evaluation/` is the retained first campaign. `results/summary/` is derived from it. `results/reproduction.json` records the clean-extraction replay comparison. A replay is successful only when every logical field matches; timing and RSS are the only excluded fields. The written universal theorems remain human proofs in `proofs/core.md`.
