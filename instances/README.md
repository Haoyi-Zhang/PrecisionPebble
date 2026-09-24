# Frozen instance selection

`campaign/` contains the exact 364 JSON inputs used by the retained evaluation. `index.json` fixes their order and the checker/oracle obligations. The files are generated deterministically by `tools/build_inputs.py`; reproduction consumes the retained files rather than silently replacing them.

The selection has seven groups:

- **Small (256):** all 16 ordered unary/binary rooted shapes with two through five vertices, crossed with four predetermined allocation/recipe profiles and capacities 8, 16, 32, and 64.
- **Extended (16):** eight predetermined seven-vertex shapes, two typed profiles, capacity 48.
- **Separation (8):** the proved ten-vertex family with `t=1,2,...,128` by powers of two, `x=2t`, `r=t`, and capacity `8t`.
- **Control (4):** the 89/91 separation, the expansive 33/35/49 valley, a unit-weight control, and a retained failed separation candidate with equal policies.
- **Hardness (2):** the affine four-state PARTITION construction for `[1,1]` and `[1,3]`; both have fourteen vertices.
- **Scaling (24):** eight predetermined sizes through 64 vertices crossed with three fixed/typed capacity settings.
- **Integer (54):** sum, dot-product, and absolute-difference-sum trees crossed with group counts 2/4/8, input bounds 7/127, and capacities `17L`, `24L`, and `32L`.

These are constructed mathematical cases, not sampled production workloads. The shape grid is exhaustive only over its stated finite enumeration. The scaling cases and integer cases are fixed coverage sets rather than statistical samples.
