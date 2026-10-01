# Preparation-aware pebbling: definitions and mathematical arguments

These are mathematical proofs written in natural language. The executable certificates check finite instances of the stated recurrence and event model; they do not constitute a mechanized proof of the theorems below. All results concern atomic, non-overwriting operators on a unique-consumer tree, not a machine with partial computations, aliasing, fragmentation, register classes, scratch space, concurrency or shared subexpressions.

## 1. Model

Let T be a finite rooted in-tree with an internal root and at least two vertices. A degenerate single-source tree is excluded from the recurrence: it has zero cost when an allowed root state is initially blue, and is otherwise infeasible. Each non-root vertex has exactly one consumer, its parent. A source has no operands. At every vertex v the precision alphabet is P={8,16,32,64}, with a positive integral allocation w(v,p). Some states may be unavailable. A source declares which representations are initially present in unbounded slow memory. An internal vertex declares finitely many recipes r=(p_1,...,p_d;q,c), where c is a nonnegative rational and d is its number of children. The recipe consumes the d operand values in the specified representations and produces a value in representation q. A front end is responsible for the semantics and admissibility of each recipe. A conversion is an explicit unary operator, not an unrecorded change of an existing value's state.

Fast memory has integer capacity B. A load or store transfers one whole value and costs its allocation. A compute event requires all operands and the newly allocated output simultaneously in fast memory; it costs c abstract work and no I/O. The executable contract has no separate hidden-workspace field: a front end must lower temporary storage to explicit values or conservatively include it in declared allocations before applying this capacity test. Red copies may be deleted freely. Slow copies have no capacity limit. Sources begin in slow memory and an allowed root representation must end in slow memory. Every source belongs to the dependency tree of the root. Operations are pure and have no side effects. Values have explicit production identities when an operation is repeated.

Minimize the pair (I/O, work) lexicographically. All comparisons and sums are exact; no floating-point tie breaking is involved. The capacity and weights are numbers encoded in binary unless a statement explicitly treats B as a numeric parameter.

A recipe is allocation-contractive when its output allocation is at most every operand allocation separately. This is stronger than being at most the sum of operand allocations. It concerns bytes/units, not the precision label: an output may widen its scalar precision while shortening its vector extent. A tree instance is contractive only if every allowed recipe satisfies this condition.

## 2. One-shot ancestry lemma

**Lemma 1.** Any successful schedule has a successful schedule that computes each internal vertex once, chooses one representation at each source, immediately discards operands after their only consumer, and has no larger I/O, work or peak allocation.

**Proof.** Select the particular blue root value that witnesses success. Trace the origin of this value backward: a stored copy refers to its red source; a load refers to the blue value it copied; a computed value refers to the operand value identities used by that compute. Continue until initially blue source values are reached. Copy chains cannot create a new logical dependency. Because the logical graph is a unique-consumer tree, the resulting computation ancestry has exactly one selected computation for each internal logical vertex and one selected state for each logical source. In particular, there cannot be two distinct selected invocations of a child that are both needed by two different consumers: that would require a shared logical descendant, excluded here.

Keep only the selected computation events and the copy events needed along the selected value-origin chains. Retain their original order. Drop every other computation and transfer. At each retained event, its selected operands are available because the backward trace retained their origins. Identity-sensitive deletion avoids confusing a surviving value with a different invocation of the same logical vertex. Removing nonselected objects and events cannot increase fast-memory occupancy. After a selected consumer executes, its selected operands have no remaining consumer, so removing their red and blue copies is safe and can only reduce memory. Nonnegative work and transfer costs imply that pruning cannot increase either objective. Every logical source is still represented because every vertex lies below the root. This proves the claim. ∎

The lemma uses the tree and purity assumptions essentially. It does not transfer to shared DAGs or to stateful operators. In the finite oracle, immediate consumption is implemented directly; Lemma 1, rather than the oracle alone, connects that finite machine to schedules initially allowed to recompute.

## 3. Spill-forest normalization

**Lemma 2.** For a fixed selected recipe assignment, an optimal schedule can be represented by a set C of internal non-root edges to spill. Each source is loaded exactly once. Each internal value whose edge is in C is stored once immediately after production, evicted, and loaded once when used by the component containing its consumer. Every other internal value remains resident from its production to its consumer. The root is stored once. The I/O of this representation is exactly

Q = sum_{sources l} w(l,p_l) + w(root,p_root) + 2 sum_{(v,parent(v)) in C} w(v,p_v).        (1)

After cutting C, all components can be executed in a bottom-up component order, each starting with empty fast memory and using the full capacity B. This last statement does not assert that a whole logical child subtree is contiguous.

**Proof.** Apply Lemma 1. For a source, only its final load before its selected consumer is useful: any earlier load followed by eviction produces nothing because there is only one selected consumer. Delete the earlier loads. The initially blue source remains available, so the final load is sufficient.

Consider an internal result. A store without a later necessary reload can be removed unless it is the terminal root store. If the result is ever evicted before consumption, retain one store and the last reload before consumption; put the store and eviction immediately after its producer. Between production and that last reload, the modified schedule uses less or equal red memory. After the last reload, keep the result to its consumer as in the original schedule. Delete extra stores and loads. If it is never usefully evicted, retain it continuously and delete unnecessary stores. These changes do not increase memory or objective. Let C be exactly the internal non-root edges with such an eviction.

Delete C from the tree. A component's sources are either original sources or the blue roots of its child components. Project the normalized schedule onto the computations and boundary loads of one component. Delete all events and live values of other components. Execute the projected trace after all its child components have finished and their roots have been stored. The required blue inputs are then available. This trace's fast-memory occupancy is at most that of the original schedule at each corresponding event. Execute the components recursively bottom-up. At each component completion, store its root and evict it; the next component starts from empty red memory. Slow copies persist and do not consume B. This gives a feasible serialized component schedule. Every original source contributes one load, every cut edge one store and one load, and the terminal root one store, establishing (1). Conversely, any such feasible component schedule is a legal pebbling and has precisely that cost. ∎

Equation (1) is an exact identity for a chosen assignment and spill forest, not just the compulsory source-and-root floor. The floor is a lower bound for every schedule with that assignment. Different assignments may have different source or root weights; optimization must not silently hold that part constant.

## 4. Resident-component exchange

**Lemma 3.** In a component with contractive selected recipes and no internal spill, fix a child branch of a vertex v, with branch root u. After the branch's first event and before u is consumed at v, its resident frontier is nonempty and has allocation at least w(u,p_u).

**Proof.** The branch begins with a boundary load or a source load. Thereafter, an internal computation replaces its live children by its output; it never removes all progress toward u. Each still-live vertex lies on a path to u consisting of uncut edges. Contractivity along this path says its allocation is at least the final allocation at u. Thus any one live frontier value witnesses the claimed bound. During non-overwriting computation, old operands and the new output coexist, which only strengthens the inequality. ∎

**Lemma 4.** A spill-free contractive component can be executed by a depth-first child order without increasing its peak memory, I/O or work. The statement remains true with any constant amount of outside resident memory reserved.

**Proof.** At a vertex v, take the branch A whose first event occurs earliest in the projected trace. Move all events of A, in their existing relative order, to the front of this trace. Its own events now see no values from the other branches, so their memory use cannot increase. Hold A's completed root while performing the remaining branches' events in their original relative order.

There is no event of another branch before A originally started. At every original event of another branch after A started, A either had an unfinished frontier or already had its completed root. Lemma 3 bounds its contribution below by its final root allocation. Replacing that contribution by the completed root therefore cannot increase memory at any other branch's load or compute event. The same argument includes the instantaneous allocation of a non-overwriting output. Dependencies are preserved because distinct child branches have no shared vertex or cross-edge. At v itself, the operand roots and output are the same objects as before.

Repeat for the remaining branches, giving a serial order of branches. Recursively apply the argument inside each branch. A constant external reservation adds the same amount to every compared occupancy and changes none of the inequalities. I/O and work do not change: no recipe or transfer was added. ∎

This is a component exchange, not a claim that all original subtrees can be serialized. Preparatory components cut out of a branch may have to run before another logical branch starts. Nor does the proof survive the weaker inequality output <= sum of operands: a frontier may then be smaller than the completed root.

## 5. Exact preparation/residency dynamic program

Fix global capacity B. For v, output state s and 0<=b<=B, let F_B(v,s,b) minimize (I/O,work) over spill forests below v with the following capacities: the distinguished resident component containing v has capacity b; every detached preparatory component has capacity B. All preparation precedes residency. The distinguished root is returned red and its store is not charged. This is a structural optimization problem; b does not mean that the outside reservation already existed while preparatory components ran.

For a source, F_B(v,s,b)=(w(v,s),0) if s is available and w(v,s)<=b, and infinity otherwise. For an internal node, consider each recipe r with output state s and operand states t_i. Let a_i=w(u_i,t_i), a=w(v,s). Reject the recipe at budget b if a+sum_i a_i>b. For each permutation pi of its children, put h_i=sum_{j before i in pi} a_j and

D_i = min( F_B(u_i,t_i,b-h_i), F_B(u_i,t_i,B)+(2a_i,0) ),                (2)

where the second choice is available only for an internal child. Then

F_B(v,s,b) = min_{r,pi} [ (0,c_r) + sum_i D_i ].                         (3)

An unavailable term is infinity. At the root rho, the answer is

min_{s allowed at rho} F_B(rho,s,B)+(w(rho,s),0).                         (4)

**Theorem 5.** Equations (2)--(4) give the lexicographically optimal unrestricted pebbling cost on every contractive instance in this model. A plan recovered from the finite minima yields a schedule with exactly that cost.

**Proof of attainability.** Induct on subtree size, simultaneously for all budgets and states. For a finite source state, load it. For a chosen internal alternative, first recursively prepare every component separated by a cut, including cuts nested within an uncut child branch. Every such preparation uses B and ends blue with empty red memory. Now traverse the distinguished component in the chosen child order. Before child i, the roots of earlier children occupy exactly h_i. For an uncut child, its recursively resident execution uses at most b-h_i; its own preparation has already happened. For a cut child, load its prepared root. The final local footprint test guarantees that all child roots and the new output coexist within b; it also implies that an individual boundary load fits. Consume the child roots, leaving v red. Charges are additive and cut edges incur precisely the extra store/load pair. Finally store the root. This constructs a feasible witness for every finite recurrence alternative.

**Proof of lower bound.** Lemmas 1 and 2 transform any schedule into a no-more-expensive spill forest. Lemma 4 gives depth-first resident components without worsening capacity. At a node of the distinguished component, this execution selects one recipe, one child order, and a keep/cut choice on each internal child edge. An uncut child is executed with exactly the previously completed child roots as outside reservation, so its distinguished capacity is b-h_i; detached preparation is still at B. A cut child is prepared as a separate full-capacity component and costs its own optimum plus 2a_i. The local compute requires a+sum_i a_i<=b. Induction therefore lower-bounds each child by its term in (2). Minimizing the allowed alternatives in (3) can only lower this cost. At the root, adding the necessary terminal store yields (4). Attainability and lower bound coincide. ∎

**Complexity.** There are at most n|P|(B+1) table entries. With bounded degree d, arithmetic operation count is O(B sum_v |R_v| d_v! d_v), plus source initialization and state indexing. A simple cut-mask checker uses an additional factor 2^d, constant for d<=3. Memory is O(n|P|B) for values and decisions. This is pseudopolynomial in binary-encoded B, not a polynomial-time dichotomy based on branching alone. Sums of at most n input rational costs have polynomial bit length in the total rational encoding, so exact arithmetic does not hide an exponential bit-size assumption. Sparse memoization may visit fewer states, but a measured sparse count is not the worst-case theorem.

## 6. Tight loss from whole-subtree contiguity

Let t>=1, x>=2t and 1<=r<=t. Capacity is B=4x. The following ten-node fixed-state tree uses unary and binary operators only:

* A is the unary result of a source of weight 4x-t, and has weight t.
* b consumes sources of weights x and 2x, producing weight x.
* c consumes sources of weights x and x+t, producing weight x.
* d consumes b and c and produces weight t.
* The root consumes A and d and produces weight r.

All recipes are contractive. The unused states may have the same positive weights, with only one state/recipe allowed. Thus this is a subfamily of the four-state model, not evidence that four active choices are required for the separation.

**Theorem 6.** The unrestricted optimum is 11x+r. The best whole-child-subtree-contiguous policy, allowing a finished child root to be stored/reloaded, costs 11x+r+2t.

**Proof.** The compulsory input/root cost is 9x+r. At least one of the edges from b and c must be spilled. Otherwise, during b's local computation, which occupies 4x by itself, c cannot have any live progress. In the normalized one-shot schedule it follows that b finishes before c starts. But then b's resident root contributes x while c computes using 3x+t, exceeding B. The symmetric possibility that c starts first already makes b impossible. Hence the extra I/O is at least 2x.

This lower bound is attained: compute b at full capacity, store and evict it; compute A, retain its t-unit result; compute c while A is held, using at most 3x+2t<=4x; load b, compute d and then the root; store the root. No other internal value is spilled. Therefore the optimum is 9x+r+2x.

For whole-subtree contiguity at the root, either A or d is completed first. If A is first and retained, the later computation of b inside d needs 4x plus the retained t units. If d is first and retained, A's source and output also need 4x plus t. Thus at least one root edge (A,root) or (d,root) must be spilled, costing another 2t. This is separate from the already necessary b/c spill. Conversely, compute and spill A, compute d using one b/c spill, reload A, and finish the root. This attains the extra 2x+2t, proving tightness. ∎

For x=2t and r=t the exact costs are 23t and 25t at B=8t: an 8% reduction relative to this restricted policy, only for this family. At x=8,t=r=1 the costs are 89 and 91 at B=32. An extra two units is not a timing or energy claim. The first attempted twelve-node example in the artifact did not separate the algorithms and is retained as a negative result.

## 7. Expansion boundary and complexity

A simple noncontractive valley example has two arms 16 -> 1 -> 8 and a root of weight 1, at B=18. The two sources contribute 32 and the output store contributes 1. Load and shrink each source to weight 1 before expanding either arm. Expanding the first arm uses 1+1+8=10; expanding the second uses 8+1+8=17; computing the root uses 8+8+1=17. Thus the compulsory floor 33 is attainable. The preparation/residency recurrence gives only an upper bound 35 here; whole-subtree contiguity gives 49. This example refutes extending Lemma 4 to arbitrary allocation-changing recipes. It does not prove that every expansive instance is hard.

**Theorem 7.** With four available precision labels, positive affine allocation functions of p/8, unary/binary operators and zero work, deciding whether an arbitrary (not necessarily contractive) in-tree attains its compulsory source-and-root I/O floor is NP-complete. The reduction is from PARTITION; no strong-hardness or complete classification of expansive instances is claimed.

**Construction.** Given any PARTITION instance on n>=2 positive integers a_i, first double every input. This preserves the answer and gives an even total S. In unscaled units define

C1 = 3S/2+1; M=C1+1;
C2 = (n+1)M+3S/2+1; K=C2+1;
B = 2K+C2; L=B-C1; H=B-C2=2K.

Create n ordinary arms and one sentinel arm. In ordinary arm i, a source of weight L is converted to a middle value of either a_i (low choice) or 2a_i (high choice). A separate source of weight H and this middle are consumed by a finalizer. The low middle produces M+2a_i; the high middle produces M+a_i. The sentinel has a source L converted to a middle of weight 1; with its separate source H, this produces a final value of weight M. Join all n+1 final values by a binary comb, whose every aggregate has weight K. All recipes have zero work. The tree has 5n+4 nodes and its mandatory I/O is

Q0=(n+1)(L+H)+K.                                                       (5)

**Phase barriers at Q0.** By Lemmas 1 and 2, a schedule attaining Q0 uses no internal spill. Any final value has weight at least M, and L+M>B because M>C1. Once a final value exists, there remains a live final/aggregate frontier of weight at least M until the root is ready. No L source can coexist with that frontier, and an already loaded L also cannot coexist at its creation. Consequently all middle values must be computed before the first finalizer.

Every aggregate has weight K and K+H>B because K>C2. After the first aggregate there is a live aggregate of weight K until the root is ready; no unconsumed H can be present or later loaded. Thus all finalizers must complete before the first aggregate. These are capacity barriers, not imposed scheduling phases.

Let x be the sum of a_i with high middles. The total middle allocation is S+x+1. During the last middle computation its L source is also live, so

L+S+x+1 <= B, hence x<=S/2.                                           (6)

The total final allocation is F=(n+1)M+2S-x. During the last finalizer, its H source and its old middle of weight at least 1 coexist with all final allocations (including the newly allocated last output). Therefore

H+F+1 <= B, hence x>=S/2.                                             (7)

Equations (6) and (7) force a partition.

**Constructive sufficiency.** Suppose x=S/2. Compute all middles first. Their total is C1, so each source-plus-current-middle computation fits L+C1=B. Then finalize ordinary arms in any order, leaving the sentinel last. At an ordinary finalization, let P be the allocation of remaining middles, including the current one. Relative to the total final allocation F, the transient live allocation excluding H exceeds F by P minus the sum of future final outputs. We have P<=C1, and the future sentinel alone weighs M>C1, so this excess is negative. These steps fit H+F<B. The sentinel finalization uses exactly H+F+1=B.

Now evaluate the comb in order. At most one previous aggregate K is resident together with unconsumed final outputs of total at most F. Allocating the next aggregate gives at most 2K+F<B, because F=C2-1. The first aggregate uses at most K+F. Store the root. The constructed schedule has no internal spill and exactly Q0 I/O.

**Affine four-state encoding.** Multiply all allocations and B by eight. Write an allocation function as w(p)=h+a(p/8), with h>=0 and a>0 integers. An L source is available only at 64 bits with h=0,a=L, giving 8L; an H source uses a=H. An ordinary middle uses h=0,a=8a_i: its 8- and 16-bit choices have sizes 8a_i and 16a_i. Its finalizer uses h=8M,a=8a_i: state 16 after a low middle has size 8M+16a_i, whereas state 8 after a high middle has size 8M+8a_i. The sentinel middle has h=0,a=8 at state 8; its finalizer has h=0,a=8M at state 8. A comb aggregate has h=0,a=2K and uses state 32, of size 8K. Only the declared transitions are allowed. All four labels occur in the construction. Sources/root have fixed states, so (5) is assignment-independent. This scaling preserves every capacity inequality.

The construction uses O(n) nodes and polynomial binary encoding: all constants are O(nS). It is therefore a polynomial reduction. Membership in NP follows from an O(n)-event one-shot, no-internal-spill witness, with recipes, source states and a topological order checked by exact integer arithmetic. The problem is NP-complete. This numerical PARTITION reduction does not establish strong NP-hardness, and no pseudo-polynomial algorithm is proved for the expansive class; accordingly, the theorem does not label the problem weakly NP-complete. The numeric role of capacity must remain explicit. ∎

## 8. Primary-source recurrence cross-check

Bhattacharjee et al. define the same four WRBPG moves used by the fixed-state specialization here: a blue-to-red load, red-to-blue store, compute when every predecessor is red, and free red deletion. Their weighted red-pebble constraint sums resident node weights, and their schedule cost sums the weights of loads and stores. Their Eq. (6) recursively chooses a permutation of complete child subtrees and, for each completed child, either keeps its root while later children run or stores/evicts/reloads that root. Eq. (7) adds the terminal root store. Lemma 3.7 and Theorem 3.8 state that this recurrence is optimal for the paper's general weighted k-ary tree class.

`src/reference_eq6.py` is a clean-room transcription of those two printed equations for fixed-state trees. It imports the local typed instance parser but does not call the preparation-aware optimizer, contiguous-policy code, oracle, or event checker. It rejects any instance with more than one source state, root state, or recipe choice, because the source equation is a fixed-weight recurrence rather than a typed extension. The following retained results are exact integers:

| Case | Capacity | Unrestricted witness / DP | Literal Eq. (6)+(7) |
|---|---:|---:|---:|
| x=8, t=r=1 | 32 | 89 | 91 |
| x=2t, r=t, t=1 | 8 | 23 | 25 |
| x=2t, r=t, t=2 | 16 | 46 | 50 |
| x=2t, r=t, t=4 | 32 | 92 | 100 |
| x=2t, r=t, t=8 | 64 | 184 | 200 |

The 89-unit trace is checked by a separately implemented move-rule replayer and reaches peak 32. Theorem 6 proves the whole family, so the table is an implementation cross-check rather than the basis of the counterexample. The conclusion is correspondingly narrow: Eq. (6) does not enumerate every unrestricted WRBPG schedule on the stated general k-ary tree class. It does not invalidate the source paper's separately structured DWT result, selected MVM tilings, hardware synthesis, or measured area/power observations. No source-paper software is copied or executed.

## 9. Exact integer-IR contract

The retained application instances are bounded vector reductions, not empirical accelerator workloads. Sources contain L signed 64-bit integers in [-a,a]. A reduction combines two length-2m vectors into length m by adding adjacent pairs from each operand. Elementwise product or absolute difference may precede the reduction tree. Grouping only reorganizes additions of exact integers; the scalar result is respectively a block sum, block dot product, or block sum of absolute differences.

Intervals are propagated with exact integers. A product uses the minimum and maximum of the four endpoint products. An absolute difference is enclosed by [0,max |x-y|] over endpoints. A reduction doubles the sum of operand lower bounds and doubles the sum of their upper bounds. A chosen representation is admitted only if this interval fits the signed range [-2^(p-1),2^(p-1)-1]. Every executed recipe thus produces an exactly representable result for every allowed source assignment, by induction on the tree. The five boundary/pseudorandom patterns are finite implementation checks of this contract, not the reason the interval argument is universally valid.

Weights are vector length times precision/8. Recipes accept equal input widths and satisfy output allocation <= each input allocation. Thus widening can be admitted when vector length halves. The abstract work proxy depends on the selected operand/output widths but is not calibrated to an instruction set. This front end proves that the contraction condition can retain precision-changing choices and exact value semantics. It does not prove that all useful mixed-precision kernels are contractive, that atomic vector instructions exist, or that abstract I/O reductions imply wall-clock or energy savings.
