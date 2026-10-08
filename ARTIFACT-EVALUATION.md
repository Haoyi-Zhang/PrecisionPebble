# Artifact Evaluation Guide

## Scope

This artifact reproduces the finite computational evidence for **Preparation-Aware Weighted Pebbling for Precision-Changing Operator Trees**. It does not mechanize the universal proofs and does not measure hardware runtime, energy, numerical error, or natural-workload prevalence. The code is deterministic, CPU-only, offline, and uses the Python standard library.

## Environment

- Python 3.10 or newer
- POSIX shell for the command block below
- approximately 200 MiB free memory and 50 MiB free disk space
- no network, solver, compiler toolchain, GPU, model API, or private dataset

## Fast checks

From the artifact root:

```sh
python3 -m unittest discover -s tests -v
python3 tools/check_controls.py --output results/reviewer-controls.json
python3 tools/check_reference_equation.py --output results/reviewer-reference-equation.json
```

Default discovery defines 60 unit tests, including three oracle-recipe controls; six descriptor controls are invoked separately. The retained Linux measurement covers 57 tests, including ten claim-evidence regressions, and does not record these added controls. Its Windows counterpart covers 49 portable tests; eight campaign-integrity tests require the POSIX `resource` module. The retained controls include three accepted positive objects, ten rejected negative/invalid objects, and five passing literal reference-equation cases. The Linux receipt and raw unit-test log in `results/measurements/` record 57 passes without skips. These retained measurements are distinct from execution of the supplied suite.

## Clean replay

```sh
rm -rf results/reviewer-replay results/reviewer-summary
for step in 1 2 3 4 5 6; do
  python3 reproduce.py --output results/reviewer-replay --chunk 64 || exit "$?"
done
python3 tools/summarize.py \
  --results results/reviewer-replay \
  --output results/reviewer-summary
python3 tools/compare_replay.py \
  --reference results/evaluation \
  --replay results/reviewer-replay \
  --output results/reviewer-replay-comparison.json
```

The replay should produce 364 checked records. The comparison should report `logical_match: true`, no validation errors, and no mismatches. Host-dependent timing and RSS fields are intentionally excluded from logical equality.

## Manuscript-linked bibliography audit

From the artifact directory inside the complete project package:

```sh
python3 tools/audit_bibliography.py \
  --tex ../paper/main.tex \
  --bib ../paper/references.bib \
  --verification bibliography-verification.csv \
  --minimum 31 \
  --output results/reviewer-bibliography-audit.json
```

## Interpretation

The event checker accepts only normalized one-shot traces. The Bellman checker recomputes a fresh recurrence table before comparing the supplied key set and costs. The claim checker binds a claimed objective to both replay paths. Successful finite checks support the implementation and retained instances; they do not replace the theorem proof.

The `audit_units` counter is a partial mixed diagnostic, not a wall-clock predictor or a whole-program operation bound. The 2,700-second campaign limit applies only to accumulated per-case body process CPU. Invocation CPU and externally measured elapsed/process-tree resources are retained separately.
