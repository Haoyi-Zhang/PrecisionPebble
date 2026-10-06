# Novelty and Scope Audit

The paper's novelty claim is intentionally narrower than “a new pebbling model” or
“the first joint precision and scheduling system.”  The contribution under review
is the combination of four precise statements:

1. a concrete and parametric counterexample to complete-logical-subtree
   enumeration in the weighted tree setting;
2. an exact two-capacity dynamic program for typed rooted in-trees under an
   allocation-contraction condition;
3. a finite expansive counterexample that identifies where the exchange proof
   fails; and
4. NP-completeness of compulsory-floor attainment for the separately defined
   four-label affine expansive class.

`novelty-matrix.csv` is generated from the verified bibliography and records the
closest and adjacent works, the dimension in which each is relevant, the material
model difference, and a claim the paper explicitly does **not** make.  The matrix
is a guard against three common positioning errors: treating a different graph or
cost model as absent prior work, presenting an application-specific correction as
a wholesale refutation, and using representation labels to imply numerical-error
or hardware-performance results that were never evaluated.

The decisive comparison with the weighted-pebbling anchor uses a literal
implementation of its restricted recurrence and a separately implemented
configuration oracle. Both share the local instance parser; neither is claimed
to be an isolated standalone implementation. These checks establish the finite
89/91 instance and support the symbolic 23t/25t argument; they do not re-run or
dispute the anchor's DWT-specific hardware study.

The rematerialization, checkpointing, distributed materialization, mixed-precision,
bit-width, scratchpad, placement, and compression literature is included because a
reviewer could reasonably ask whether one of those systems already solves the same
problem.  The matrix makes the answer auditable by comparing graph class, operator
semantics, memory model, cost objective, and guarantee rather than relying on title
similarity.
