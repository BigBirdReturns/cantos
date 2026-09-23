# Run 2 · post-hoc exploration (NOT pre-registered, never the headline)

Written 2026-09-23 after seeing the first pre-registered AMD cells. The pre-registered serve (AITER on, all else default)
auto-selected `ROCM_ATTN` attention ("incompatible backend TURBOQUANT ... overriding") and `RowWiseTorchFP8ScaledMMLinearKernel`
for FP8 linears; decode at c1 ran ~28 ms/token. This exploration asks one question: how much does forcing AMD's own
attention backend (`--attention-backend ROCM_AITER_FA`) change the same cells? Everything else is identical to arm2.sh.

Cells: one repeat of long c1/c8/c32 and short c1/c8/c32/c64, same prompts and seeds as repeat 0. Results live in
/tmp/run2-explore on the machine and `results/run2-explore-<arm>` here, labelled exploratory. They can support a
"default vs tuned" note to the provider; they do not replace or amend the pre-registered result.
