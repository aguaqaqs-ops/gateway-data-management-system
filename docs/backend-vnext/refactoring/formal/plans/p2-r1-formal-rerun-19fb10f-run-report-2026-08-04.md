# P2-R1 Provider Feasibility Decision

- p2_r1_exit: `no-go`
- selected_provider: `None`
- next_round_ready: `False`
- p2_r2_ready: `False`
- decision_kind: `formal`

| Candidate | Workflow | 60m safety | W1 max import (s) | Capacity projection | Hard gate |
|---|---:|---:|---:|---:|---:|
| candidate_a_offline_cli | True | True | 80.57398188298976 | 3002.46 | False |
| candidate_b_sql_server | True | True | 102.21576332999393 | 2366.76 | False |

Normal and same-shape scaling coverage are required together for a formal decision.
All workloads are deterministic synthetic fixtures; results are feasibility measurements, not production SLOs.
W3 is storage evidence measured after provider shutdown and filesystem quiesce; it has no fixed ratio hard gate.
