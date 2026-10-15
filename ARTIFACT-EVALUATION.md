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
python3 -B tests/recipe_descriptor_regression.py -v
work=$(mktemp -d "${TMPDIR:-/tmp}/precision-pebble-checks.XXXXXX")
python3 tools/check_controls.py --output "$work/controls.json"
python3 tools/check_reference_equation.py --output "$work/reference-equation.json"
```

Default discovery includes three oracle-recipe controls, two added bibliography-ledger controls, and current semantic-admission controls for the complete five-pattern integer profile; six descriptor controls are invoked separately. The retained Linux measurement covers 57 tests, including ten claim-evidence regressions, and predates these added controls. Its Windows counterpart covers 49 portable tests; eight campaign-integrity tests require the POSIX `resource` module. The retained controls include three accepted positive objects, ten rejected negative/invalid objects, and five passing literal reference-equation cases. The Linux receipt and raw unit-test log in `results/measurements/` record 57 passes without skips. These retained measurements are distinct from execution of the supplied suite.

## Clean replay

Use the complete command block in the README's **Requirements and clean reproduction**
section. It allocates a new temporary directory outside the repository, runs six
resumable chunks and the checks above, then summarizes and compares the replay.
Keep that directory to inspect raw outputs; no prior run needs to be deleted.

The replay should produce 364 checked records. The comparison should report `logical_match: true`, no validation errors, and no mismatches. Host-dependent timing and RSS fields are intentionally excluded from logical equality.

## Manuscript-linked bibliography audit

From the artifact directory inside the complete project package:

```sh
work=$(mktemp -d "${TMPDIR:-/tmp}/precision-pebble-bibliography.XXXXXX")
python3 tools/audit_bibliography.py \
  --tex ../paper/main.tex \
  --bib ../paper/references.bib \
  --verification bibliography-verification.csv \
  --minimum 51 \
  --allow-ledger-identifiers \
  --output "$work/bibliography-audit-current.json"
```

The current ledger covers all 51 cited keys: 31 historical rows are retained,
and 20 additional rows record primary-source metadata and bounded citation
context, not complete-source reading. The explicit ledger-identifier option
uses a DOI or primary-source record URL where the frozen formal citation omits
an inline identifier; it does not waive key, title, year, date, status, or
existing-identifier consistency checks. This audit checks local consistency,
not source truth or citation entailment. Historical audit results and the
separate full-text reading cohort remain unchanged.

## Interpretation

The event checker accepts only normalized one-shot traces. The Bellman checker recomputes a fresh recurrence table before comparing the supplied key set and costs. The claim checker binds a claimed objective to both replay paths. Successful finite checks support the implementation and retained instances; they do not replace the theorem proof. No statistical fitting or held-out workload study is performed. The optimizer, oracle and checkers share the written model, so a common specification error remains possible.

The `audit_units` counter is a partial mixed diagnostic, not a wall-clock predictor or a whole-program operation bound. The 2,700-second campaign limit applies only to accumulated per-case body process CPU. Invocation CPU and externally measured elapsed/process-tree resources are retained separately.
