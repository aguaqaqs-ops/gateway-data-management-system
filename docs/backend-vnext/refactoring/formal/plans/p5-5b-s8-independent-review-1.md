# P5-5B-S8 Independent Review 1 — S8-F1 Remediation Closure

状态：**PASS — S8-F1 closed；S8 gate provenance 可复核**

日期：2026-09-18 (UTC+8)

Owner：Independent reviewer（read-only；本文件是唯一写入）

> **Follows** [p5-5b-s8-f1-remediation-handoff.md](p5-5b-s8-f1-remediation-handoff.md)、
> [p5-5b-s8-handoff.md](p5-5b-s8-handoff.md)

## 1. Decision

```yaml
stage: P5-5B-S8-s8-f1-remediation-closure
review_target: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
gate_candidate: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
test_hygiene_seal: 87c497634e4f6417de7fbb46b42086fd61af9031
test_hygiene_fix_seal: 460d6f5b1efdb24199534778bd5cc9d4a8131d13
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
records_head: pending_hygiene_seal
parent_review: p5-5b-s7-independent-review-8.md
authority:
  - p5-5b-s8-f1-remediation-handoff.md
  - p5-5b-submit-finalize-execution-plan.md §6.2 / §7 / §8
decision: pass
findings_closed: [S8-F1]
findings_open: []
implementation_authority_unchanged: true
five_package_static: pass
authoritative_runner: pass
container_rebuild_required: no
container_reason: S8-F1 test-only; backend Dockerfile copies backend/src only
s8_gate_evidence: p5-5b-s8-handoff.md
p5_5b_slice_exit: pass_recommended
p5_5c_authorized: no
production_deployment_authorized: no
timezone: Asia/Shanghai
```

## 2. Changed paths audit（`87c49763..460d6f5b`）

| Path | Role |
| --- | --- |
| `vnext/backend/tests/test_live_session.py` | S8-F1：`Iterator[None]` mypy fix（test-only） |

`git diff --name-only 87c49763..460d6f5b` 与上表完全一致，无 missing/extra。

## 3. S8-F1 closure verification

### 3.1 Static gates

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
# pass

for pkg in shared_kernel repository_contracts repository_client backend repository_service; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
# all pass
```

### 3.2 Authoritative runner

```bash
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
# exit 0; shared_kernel 242; repository_contracts 152; repository_client 154;
# backend 2184 passed 1 skipped; repository_service parallel 1678 passed 1 skipped;
# repository_service serial 205 passed
```

### 3.3 Retroactive authority

`test_live_session.py` autouse fixture 在 `test_hygiene_seal` @ `87c49763` 引入时无独立
finding 记录；本 review 以 S8-F1 retroactive authority 闭合，不扩大 production allowed paths。

## 4. Provenance

### 4.1 Source-tree digest

**Method:** `sorted_per_file_sha256_records_for_git_ls_files_vnext`

```bash
git ls-files 'vnext/**' \
  | LC_ALL=C sort \
  | while IFS= read -r f; do
      printf '%s\t%s\n' "$f" "$(sha256sum "$f" | awk '{print $1}')"
    done \
  | sha256sum \
  | awk '{print "sha256:" $1}'
```

| Gate object | Digest | File count |
| --- | --- | --- |
| `460d6f5b`（current gate candidate） | `sha256:700d77136bae43c356e0270404ad83dda1a5a8438ead3398826bb5e99160c359` | 860 |
| `87c49763`（prior gate candidate） | `sha256:4fe713c846ee0b3152f667a87ebe538c8eccc87d813533c3e5f96696f854218b` | 860 |

S8 handoff 原记 `sha256:15e496bb…` **不可复现**（与 P4-R5 §8 historical digest correction 同类）；
以本 review 写死配方及 `460d6f5b` 实测值为准。

### 4.2 Container disposition

`backend/Dockerfile` 仅 `COPY backend/src`；S8-F1 不触碰 build input。三镜像 ID 与 S8
handoff 记录一致（`6309926b…` / `3ce44246…` / `a725a242…`）；**不重建**。

### 4.3 records_head

Hygiene content-seal SHA（publication pin commit 的 parent）；语义见
[p5-5b-s8-handoff.md](p5-5b-s8-handoff.md) Hygiene 块。须 `git branch -a --contains` 可达。

## 5. Next step

```yaml
p5_5b_slice_exit: pass_recommended
next_step: independent_acceptance_authority_for_slice_exit_declaration
p5_5c_authorized: no
production_deployment_authorized: no
```
