# P2-R1 Formal No-Go Decision Record

- Decision: `no-go`
- Selected provider: `null`
- P2-R2 ready: `false`
- Decision scope: this exact formal rerun only

## Source and provenance

- Commit: `19fb10fb733cd5e43c6fe7a13b743fc9b90edf41`
- Image: `sha256:8641fbb2adeff7888a973fdd7a6a66b7a06a85ba27e54ec15834937a8d621068`
- Source tree digest: `sha256:2b9f1f1023c42eaaf8da0f6d71037643381f63e6f87c927a0270c683e7b01fc8`
- Lock SHA-256: `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`
- Dolt/uv/connector/PyArrow: `2.1.11` / `0.11.28` / `9.7.0` / `25.0.0`
- Cache condition: `retained-dependency-cache`

Artifacts:

- [raw JSONL](p2-r1-formal-rerun-19fb10f-raw-2026-08-04.jsonl) — SHA-256 `421ec4ff0de60e0e13782a98be04c3539de76ee46eee3d54b94703ae6fee7a1d`
- [summary JSON](p2-r1-formal-rerun-19fb10f-summary-2026-08-04.json) — SHA-256 `9fc7020b463299bc861ea2a0082f2f6851d0e91569d3c7fdcfdd107e9aac202a`
- [launcher report](p2-r1-formal-rerun-19fb10f-run-report-2026-08-04.md) — SHA-256 `e0e8f0971fdb321b8116cae07e8514a9de18eb5eed4f5396d6580ee3165e6678`
- [offline failure analysis](p2-r1-formal-rerun-19fb10f-failure-analysis-2026-08-04.json)
  — SHA-256 `be07861bff56ce9039bb454ac51c13278c18dc0c862418498f0f7cc16a160611`

## Coverage and correctness

- Records: `132/132`; unique keys `132`; duplicate keys `0`.
- Normal coverage: `True`; scaling coverage: `True`.
- Execution errors: `0`; correctness failures: `0`; W3 storage failures: `0` (`0` unavailable).
- Both candidates passed workflow correctness, safety, metadata, storage provenance and W3 lifecycle evidence.

## Bounded-stream hard-gate failures

Authority requires a candidate to pass every bounded dimension; a ratio greater than `1.5` is a hard failure and is not treated as noise.

| Candidate | Row bound | Subject/window | Ratio | Max scale/peak | Min scale/peak |
|---|---:|---|---:|---|---|
| candidate_a_offline_cli | 256 | workflow_process_tree/first_10pct | 1.532771 | S100=269688 | S10=175948 |
| candidate_a_offline_cli | 256 | workflow_process_tree/middle_10pct | 1.683209 | S100=300244 | S10=178376 |
| candidate_a_offline_cli | 256 | workflow_process_tree/final_10pct | 1.729610 | S100=319708 | S10=184844 |
| candidate_a_offline_cli | 256 | provider_process_tree/first_10pct | 1.577121 | S100=250308 | S10=158712 |
| candidate_a_offline_cli | 256 | provider_process_tree/middle_10pct | 1.717149 | S100=276516 | S10=161032 |
| candidate_a_offline_cli | 256 | provider_process_tree/final_10pct | 1.744675 | S100=291912 | S10=167316 |
| candidate_a_offline_cli | 256 | cgroup/first_10pct | 2.358556 | S100=165593088 | S10=70209536 |
| candidate_a_offline_cli | 256 | cgroup/middle_10pct | 2.560277 | S100=168325120 | S10=65744896 |
| candidate_a_offline_cli | 256 | cgroup/final_10pct | 2.371483 | S100=188502016 | S10=79486976 |
| candidate_a_offline_cli | 1024 | workflow_process_tree/first_10pct | 1.558994 | S100=278692 | S10=178764 |
| candidate_a_offline_cli | 1024 | workflow_process_tree/middle_10pct | 1.643034 | S100=305072 | S10=185676 |
| candidate_a_offline_cli | 1024 | workflow_process_tree/final_10pct | 1.668066 | S100=324272 | S10=194400 |
| candidate_a_offline_cli | 1024 | provider_process_tree/first_10pct | 1.617076 | S100=256520 | S10=158632 |
| candidate_a_offline_cli | 1024 | provider_process_tree/middle_10pct | 1.732819 | S100=282900 | S10=163260 |
| candidate_a_offline_cli | 1024 | provider_process_tree/final_10pct | 1.803324 | S100=302100 | S10=167524 |
| candidate_a_offline_cli | 1024 | arrow_memory_pool/first_10pct | 2.000000 | S40=496512 | S10=248256 |
| candidate_a_offline_cli | 1024 | cgroup/first_10pct | 2.492736 | S100=186245120 | S10=74715136 |
| candidate_a_offline_cli | 1024 | cgroup/middle_10pct | 2.475773 | S100=187523072 | S10=75743232 |
| candidate_a_offline_cli | 1024 | cgroup/final_10pct | 2.627912 | S100=212566016 | S10=80887808 |
| candidate_b_sql_server | 256 | workflow_process_tree/first_10pct | 2.042322 | S40=20268 | S10=9924 |
| candidate_b_sql_server | 256 | workflow_process_tree/middle_10pct | 3.954955 | S40=47412 | S10=11988 |
| candidate_b_sql_server | 256 | workflow_process_tree/final_10pct | 4.083958 | S100=65376 | S10=16008 |
| candidate_b_sql_server | 256 | provider_process_tree/first_10pct | 864.333333 | S40=10372 | S10=12 |
| candidate_b_sql_server | 256 | provider_process_tree/middle_10pct | 18.106178 | S40=37516 | S10=2072 |
| candidate_b_sql_server | 256 | provider_process_tree/final_10pct | 8.991558 | S100=55388 | S10=6160 |
| candidate_b_sql_server | 256 | cgroup/first_10pct | 2.259015 | S40=18219008 | S10=8065024 |
| candidate_b_sql_server | 256 | cgroup/middle_10pct | 4.343462 | S40=46256128 | S10=10649600 |
| candidate_b_sql_server | 256 | cgroup/final_10pct | 4.746055 | S100=65298432 | S10=13758464 |
| candidate_b_sql_server | 1024 | workflow_process_tree/middle_10pct | 1.605634 | S100=42864 | S10=26696 |
| candidate_b_sql_server | 1024 | workflow_process_tree/final_10pct | 2.603624 | S100=69548 | S10=26712 |
| candidate_b_sql_server | 1024 | provider_process_tree/first_10pct | 2.071150 | S10=8500 | S40=4104 |
| candidate_b_sql_server | 1024 | provider_process_tree/middle_10pct | 2.271433 | S100=28720 | S10=12644 |
| candidate_b_sql_server | 1024 | provider_process_tree/final_10pct | 4.379943 | S100=55380 | S10=12644 |
| candidate_b_sql_server | 1024 | arrow_memory_pool/first_10pct | 2.000000 | S40=496512 | S10=248256 |
| candidate_b_sql_server | 1024 | cgroup/middle_10pct | 1.602620 | S100=43593728 | S10=27201536 |
| candidate_b_sql_server | 1024 | cgroup/final_10pct | 2.665388 | S100=71159808 | S10=26697728 |

Online gate stops at the first failure; the complete offline dimension/scale/sample data is in the failure-analysis JSON. It includes all five measured values per S10/S40/S100, baseline-adjusted and absolute plateaus, peak sample origins, and same-window subject comparisons.

## Decision and next action

- Candidate A bounded gate: `fail`.
- Candidate B bounded gate: `fail`.
- No provider is selected and P2-R2 is not authorized.
- This record does not relax the `1.5` threshold or infer a root cause. Any follow-up must be a targeted diagnostic of the listed dimensions; a new formal matrix requires a confirmed implementation/methodology change and a new immutable provenance run.
