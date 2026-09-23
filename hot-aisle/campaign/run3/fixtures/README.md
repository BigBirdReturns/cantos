# Offline fixtures and provenance

The five tiny tasks are authored test fixtures, not copied EvalPlus tasks.
The CODE-shaped slice is synthetic and tests timestamp parsing, ties, boundaries and scaling;
it is not an observed Azure slice. Production must use the source file and verified SHA in
SOURCES.md. Fixture task IDs are deliberately isolated by synthetic=true.

- serve-amd.log: verbatim selected linear-kernel and override lines copied from
  ../../results/run2-hotaisle-mi300x/serve.log (the real Llama 70B Run 2 log).
  The candidate list is not a list of selected backends. This is parser evidence, not
  evidence that Run 3's Qwen block-FP8 model uses the same kernel.
- serve-amd-exploration.log: the two observed exploration lines quoted in the Fix Round 1
  brief, transcribed without invented timestamps. The full exploration log was not supplied.
- serve-nvidia.log: explicitly AUTHORED. No real CUDA log exists on disk for this build.

No fixture establishes Run 3 model quality, GPU performance or upstream dataset-byte verification.
