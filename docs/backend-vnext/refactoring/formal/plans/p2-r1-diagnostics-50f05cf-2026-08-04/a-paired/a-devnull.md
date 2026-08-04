# P2-R1 Provider Feasibility Decision

- p2_r1_exit: `no-go`
- selected_provider: `None`
- next_round_ready: `False`
- p2_r2_ready: `False`
- decision_kind: `diagnostic`

| Candidate | Workflow | 60m safety | W1 max import (s) | Capacity projection | Hard gate |
|---|---:|---:|---:|---:|---:|
| candidate_a_offline_cli | False | False | None | 0.00 | False |
| candidate_b_sql_server | False | False | None | 0.00 | False |

Normal and same-shape scaling coverage are required together for a formal decision.
All workloads are deterministic synthetic fixtures; results are feasibility measurements, not production SLOs.
W3 is storage evidence measured after provider shutdown and filesystem quiesce; it has no fixed ratio hard gate.
