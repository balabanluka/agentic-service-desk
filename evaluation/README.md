# V2 Evaluation Data

This directory contains original synthetic evaluation data for the frozen
Harborlight Cloud knowledge corpus. Development datasets may guide implementation
work. Held-out datasets are frozen benchmarks: do not change their cases after
observing their results. `workflow-v1.json` remains the historical pre-fix
benchmark; `workflow-v2.json` is the separately frozen post-fix workflow set.
The manifests record SHA-256 fingerprints of normalized UTF-8 held-out JSON
content and are verified by the evaluation CLI.

The datasets evaluate retrieval ranking and deterministic workflow contracts.
They do not claim that string matching can prove answer-level factual accuracy.
The explicit live workflow mode records answers for human review; it is never run
by pytest and requires a manual confirmation flag because it uses OpenAI APIs.

Generated reports belong in `evaluation/reports/`, which is intentionally ignored.
