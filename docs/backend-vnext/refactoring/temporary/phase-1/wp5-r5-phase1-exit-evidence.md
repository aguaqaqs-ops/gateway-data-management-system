# WP5 R5 — Phase 1 Exit Evidence (pre-commit candidate)

状态：**WP5 R5 pre-commit candidate** — `PR-CORRECTNESS` / `PR-NATIVE` 已在当前工作区快照通过；`PHASE-EXIT-CONTAINER` 为 **BLOCKED**（Docker Hub 拉取超时）且正式 gate 因 **dirty worktree** fail-closed。**未宣布 Phase 1 complete。**

日期：2026-07-25

Gate：`PR-CORRECTNESS` + `PR-NATIVE` + `PHASE-EXIT-CONTAINER`

---

## 1. Scope / non-goals

| 项 | 声明 |
| --- | --- |
| 本轮范围 | `PHASE-EXIT-CONTAINER`（`gate.sh phase-exit-container`）、digest-pinned 镜像/Compose、wheel-in-image、health/native smoke、immutable identity、R5 Patch SHA、phase ledger 更新 |
| **不是** | Phase 1 complete（无 exact-commit 三 gate 全绿）、镜像 push/registry 发布、第二个 scenario、numeric 性能声明、自动 bless |

---

## 2. Authority

- `implementation-stages.md` §4 Phase 1 exit / gate classes
- `phase-1-implementation-design-and-delivery-plan.md`
- `fixture-oracle-and-conformance.md`
- `canonical-row-hash-compute-boundary.md`
- `shared-canonical-encoding.md`
- `rust-safety-and-performance-policy.md`
- `wp3-wp5-checkout-plan.md`
- WP3 R5、WP4 R4、WP5 R1–R4 accepted evidence

---

## 3. Baseline / identity

| 项 | 值 |
| --- | --- |
| R4 accepted commit | `b747590ac6ffdfe0e00b320363ce429e663e358e` |
| Candidate HEAD | `b747590ac6ffdfe0e00b320363ce429e663e358e`（**未提交 R5 变更**） |
| Branch | `main` |
| merge-base(HEAD, R4) | `b747590ac6ffdfe0e00b320363ce429e663e358e` |
| 工作区 | **dirty**（R5 实现文件 modified + untracked） |
| R5 Patch SHA（排除本 evidence） | 见 §10 |
| 最终 commit SHA | **无**（pre-commit） |

---

## 4. 变更摘要

- `vnext/scripts/gate.sh`：`phase-exit-container` 子命令；`export EXPECTED_HEAD` 绑定当前 `HEAD`
- `vnext/scripts/phase_exit_container_gate.sh`：身份/lock/build/smoke/compose/cleanup/BLOCKED
- `vnext/deploy/phase-1-image-pins.env`：base image `@sha256` 固定；`UV_PIP_WHEEL_URL` + `UV_PIP_WHEEL_SHA256`
- `vnext/backend/Dockerfile`：**单阶段** runtime；host 暂存 gateway wheel + **uv wheel** COPY + `sha256sum -c`；**无** 镜像内 `maturin` / **无** 浮动 `pip install uv`
- `vnext/deploy/compose.phase-exit.yaml`：预构建 `image` + `--no-build`；与 gate `image_id` 绑定
- `vnext/backend/pyproject.container.toml` + `uv.container.lock`：容器 runtime 无 path native dep
- `gateway_backend.container_native_smoke`：canonical row-hash oracle + `result_jcs` contract；负向单测
- `vnext/deploy/compose.yaml`：默认 `image:`（`PHASE_EXIT_IMAGE_TAG`）；`legacy-build` profile 保留可选 build
- `vnext/.dockerignore`：排除 `rust/`；`backend/.phase-exit-build/` gitignore
- Identity 落盘：`docs/.../phase-1/artifacts/phase-exit-container-identity-<sha256>.json`（content-addressed；`latest` 非权威；gitignore，body+cleanup 双成功后原子写入）
- `verify-wp5-r5-patch-sha.sh`、`test_phase_exit_container_gate.py`
- `test_wp5_r4_profile_matrix.py`：R4 patch SHA 守卫仅在 exact R4 树执行

---

## 5. Toolchain / locks / pins

| 组件 | 版本 |
| --- | --- |
| uv | 0.11.28 |
| Python | 3.14.6 |
| Rust | 1.97.0 |
| Docker / Compose | 29.6.1 / 5.3.1（daemon 可用） |

### Lock SHA-256（构建前后未变）

| 文件 | SHA-256 |
| --- | --- |
| `vnext/rust/Cargo.lock` | `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544` |
| `vnext/backend/uv.lock` | `681a3f4e4b0ff0b4890761736f8dd35e8a84afaebc8cf2310ccf3221adde680c` |
| `vnext/backend/uv.container.lock` | `bcba4053815b214bba6696944e09bfb073f9d9928818c78008143315e3305995` |
| `vnext/shared_kernel/uv.lock` | `fe79bf4df1231bf308ad19614a0b5690ef1e5489a0b99d8194e8f363e36e4f74` |
| `vnext/conformance/uv.lock` | `36091eadcfd8fde94983d4d843f095494f493ce75da02049415b574c468575d4` |
| `vnext/repository_service/uv.lock` | `e52d6b8c9720ed2eecebd0ba3ef3bdeca4435a525422b874f299abeba30f17f1` |

### Base image pins（`vnext/deploy/phase-1-image-pins.env`）

- `RUST_BUILDER_IMAGE=docker.io/library/rust:1.97.0-bookworm@sha256:8fa55b2f3ddf97471ab6a767bfa3f37e6bad0986ba823e75fea57e2a2a5c3073`
- `PYTHON_RUNTIME_IMAGE=docker.io/library/python:3.14.6-slim-bookworm@sha256:4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9`
- `UV_PIP_WHEEL_URL` / `UV_PIP_WHEEL_SHA256`：`uv==0.11.28` manylinux x86_64 wheel（gate 下载至 `backend/.phase-exit-build/<PEP427-basename>`，Docker build-arg `UV_WHEEL_BASENAME` + `UV_WHEEL_SHA256` 校验）

### Wheel / image identity（remediation 后模型）

- **唯一权威 wheel**：host `maturin build --release --locked --offline`（与 `PR-NATIVE` 同源）。
- Gate 将 maturin 产物以 **原始 PEP 427 basename** 暂存至 `backend/.phase-exit-build/`；Dockerfile `COPY`（`GATEWAY_COMPUTE_WHEEL_BASENAME`）+ build-time `sha256sum -c`；`GATEWAY_INSTALLED_WHEEL_PATH` 指向镜像内同 basename。
- **uv / pip**：pins 合法 basename staging；`uv-cli-venv` 经 `--without-pip` + 钉扎 pip wheel（`PYTHONPATH` + `python -m pip`）引导，再装 uv；identity JSON 含 `host_pip_version`；deps：`uv export --frozen --no-dev --no-hashes --no-annotate` → **`filter-export`**（去 hash/注释/`-e`、跳过 `sys_platform == 'win32'`）→ **`uv.container.lock` 选 CDN wheel**（`py3-none-any` / `py2.py3-none-any` 或 `cp314`+`manylinux`+`x86_64`）；select **落盘并校验非空** 后逐包 **`curl` + `http_code` + lock `sha256`**；CDN **408/429/5xx 或 transport → exit 3**；**404 / sha / 空清单 → exit 1**。
- `container_native_smoke` 校验 **wheel/extension**、**exact row hashes**、**result_jcs** digests；gate `docker run` 复验 wheel+extension 字节。
- Gate：`assert_host_toolchain_matches_pins`（pinned `uv` wheel venv + `rustc`/`python`）；`docker pull`：**124 / 非 local stderr → exit 3**，malformed ref（**收窄** stderr allowlist，不含 `manifest invalid`）→ exit 1；curl：`phase_exit_curl_fetch_to_file` 经 stdout **`ec<TAB>http_code`** 回传；curl transport ec 含 **16/18/92/95/96/97**（97=proxy handshake；含截断 `Content-Length` 活探针 → exit 3）；pin/deps wheel 共用 **HTTP 408/429/5xx 或 transport → exit 3**，**404 → exit 1**；平台 manylinux 轮精确 **`-cpXY-cpXY-`**（拒绝 `cp314t` 子串误选）；**offline** `docker build` → exit 1；`deps-classify-regression` 含 **`export-select-regression`**、curl ec 回归、截断 fetch、deps-wheel 503/404、`select-regression`、真实 `127.0.0.1:1` fetch 探针；healthz JSON `status==ok`。
- **容器镜像 identity 实证**：仍 **BLOCKED**（registry 未通）；模型已闭合，待 clean exact commit 重跑。

### `EXPECTED_HEAD`（正式 gate）

- `gate.sh phase-exit-container` 在 `exec` 前 `export EXPECTED_HEAD=$(git rev-parse HEAD)`。
- `assert_head_identity`：非 regression inject 时 `EXPECTED_HEAD` 必填且必须等于当前 `HEAD`（fail-closed）。
- 单测 / 子命令绕过 `gate.sh` 时须自设 `EXPECTED_HEAD`，或仅用 `check-static` / `verify-registry-blocked` / `success-path-regression`（`REGRESSION_MODE=1`）。

---

## 6. Gate 命令与结果（当前 dirty 快照）

| 命令 | Exit | 摘要 |
| --- | ---: | --- |
| `git diff --check` | 0 | 无冲突标记 |
| `pytest tests/test_phase_exit_container_gate.py` | 0 | **48 passed, 1 skipped**（快照 2026-07-26 curl transport + ABI 批） |
| `pytest tests/test_phase_exit_identity_bundle.py` | 0 | **7 passed** |
| `pytest vnext/backend/tests/test_container_native_smoke.py` | 0 | **10 passed** |
| `bash …/phase_exit_container_gate.sh trap-regression` | 0 | cleanup 失败传播 |
| `bash …/phase_exit_container_gate.sh success-path-regression` | 0 | inject 成功路径 + cleanup |
| `bash vnext/scripts/gate.sh correctness` | 0 | conformance **629 passed, 4 skipped**；backend **255 passed, 3 skipped**；`/tmp/wp5-r5-consolidate-correctness6.log` |
| `bash vnext/scripts/gate.sh native` | 0 | pr_native **57** + conformance **3**；`/tmp/wp5-r5-consolidate-native2.log` |
| `bash vnext/scripts/gate.sh phase-exit-container` | 1 | **dirty worktree** fail-closed |
| `PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT=1` + `verify-registry-blocked` | 3 | **BLOCKED:** pull timeout inject |
| `PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED=1` | 3 | **BLOCKED:** registry inject |

---

## 7. Required scenario matrix

正式 `data.canonical-row-hashes.mixed-scalars` 四 cell（reference / integration / provider-matrix×2）在 `test_formal_matrix_four_cells_all_passed` 闭包内 **PASSED**（与 WP5 R4 一致，无 skip/xfail/UNSUPPORTED）。

Integration：facade → PyO3 → Rust → ArtifactRef → fresh reopen（harness 路径未改）。

---

## 8. Structural performance evidence（汇总，无 numeric 声明）

引用 WP4 R4 §11 / WP3 R5 sign-off：

- PyArrow 25.0.0；Rust 1.97.0；GIL 探针 workload 4096 rows / 16×256 batches
- Python row materialization count：**0**（architecture 测试）
- Memory breakdown 上界：input 16384 B / hash-sort 131072 B / production IPC 131352 B（见 `wp4-r4-artifact-path-closure.md` §11）
- **不作** throughput/latency 收益声明

---

## 9. Governance / blocking register

| ID | Owner | 状态 | 处置 |
| --- | --- | --- | --- |
| CONTAINER-REGISTRY | 环境/infra | **BLOCKED** | Docker Hub `registry-1.docker.io` 拉取超时；恢复网络后在 **exact commit + 干净树** 重跑 `phase-exit-container` |
| R5-PRECOMMIT | 实现 | **OPEN** | 用户授权后单提交 R5，再重跑三 gate |
| WP5-R3-EVIDENCE-HOLD | 审核 | **DEFERRED** | R3 evidence 仍为 CONDITIONAL HOLD（与 R4 并列登记） |
| WP5-R4-EVIDENCE-HOLD | 审核 | **DEFERRED** | R4 evidence 仍为 CONDITIONAL HOLD；R5 不伪造外部 PASS |
| CONTAINER-WHEEL-IDENTITY | 实现 | **FIXED（模型）** | PEP 427 合法 wheel basename staging + COPY；host/image 双重复验；**registry 实证待重跑** |
| CONTAINER-COMPOSE-IDENTITY | 实现 | **FIXED（模型）** | `compose.phase-exit.yaml` + `--no-build` + `image_id` 断言 |
| PHASE-EXIT-ALLOW-DIRTY | 实现 | **FIXED** | 正式 gate 拒绝 `ALLOW_DIRTY=1` |
| PHASE-EXIT-INJECT-BYPASS | 审核 | **FIXED** | 正式 `gate` 拒绝 `INJECT_BODY_SUCCESS`/`REGRESSION_MODE`；仅 regression 子命令可用 |
| CONTAINER-UV-PIN | 审核 | **FIXED（模型）** | `UV_PIP_WHEEL_*` + `PIP_WHEEL_*` + pinned pip bootstrap；**registry 实证待重跑** |
| PHASE-EXIT-EXPECTED-HEAD | 审核 | **FIXED** | `gate.sh` 绑定；正式 gate 必填且等于 `HEAD` |
| CONTAINER-NATIVE-SMOKE-ORACLE | 审核 | **FIXED（模型）** | exact `result_jcs` bytes + 单列 Arrow schema；负向单测；**registry 实证待重跑** |
| CONTAINER-CLEANUP-IDENTITY | 审核 | **FIXED（模型）** | content-addressed 落盘；image-side 字段；persist 预计算路径 + 失败必 rollback；**registry 实证待重跑** |
| CONTAINER-TOOLCHAIN-PIN | 审核 | **FIXED** | host `uv`/`rustc`/`python` vs pins；gate 用 pinned uv wheel venv |
| CONTAINER-NETWORK-DEADLINE | 审核 | **FIXED（模型）** | lock CDN deps + curl **ec+http_code** + sha256；408/429/5xx + transport → 3；404/sha/无 wheel → 1；pull **local ref only** → 1（`manifest invalid` → 3）；offline build → 1；**registry 实证待重跑** |
| COMPOSE-DEFAULT-IMAGE-ONLY | 审核 | **FIXED（模型）** | 默认 `compose.yaml` 四变量 `docker compose config -q`；legacy→`compose.legacy-build.yaml` |

---

## 10. Patch SHA

```bash
BASE=b747590ac6ffdfe0e00b320363ce429e663e358e \
  EXPECTED_SHA=457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3 \
  bash vnext/scripts/verify-wp5-r5-patch-sha.sh
```

EXPECTED_SHA=457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3

### Auditor + remediation note (2026-07-25)

- **Audit fixed:** EXIT trap (`phase_exit_exit_trap`)、`git diff --quiet HEAD`、success-path-regression。
- **Remediation fixed:** host-only wheel staging、单阶段 Dockerfile、wheel 文件 SHA smoke、`compose.phase-exit.yaml` 无 rebuild、正式 gate 禁止 `ALLOW_DIRTY`、`uv.container.lock` 纳入 lock 监控、`verify-registry-blocked` 子命令。
- **Re-audit fix:** 正式 `gate` 拒绝 `INJECT_BODY_SUCCESS` / `REGRESSION_MODE` / `SKIP_PLATFORM_CHECK`；inject 仅限 `success-path-regression` → `run_phase_exit_gate_shared`。
- **Still HOLD:** registry **BLOCKED**；无 clean exact-commit `PHASE-EXIT-CONTAINER` PASS。
- **Consolidated review fix (2026-07-26):** B1 smoke oracle；B2 cleanup/tag；M1 toolchain + pinned uv CLI；M2 identity artifact；M3 network deadline；M5 compose default image；Moderate extension/healthz/dockerignore/gitignore。
- **R5 re-review fix (2026-07-26):** B1 content-addressed identity after body+cleanup；M1 deadline 1–3600 + offline deps wheelhouse + build timeout；M2 closed smoke bytes/schema；M3 `compose.legacy-build.yaml` + default `config -q`；M4 cleanup_ec 闭环；正式 gate 禁 `FORCE_CLEANUP_FAIL`/`INJECT_RMI_FAIL`/`INJECT_TMP_RM_FAIL`。
- **R6 residual fix (2026-07-26):** identity `direct_url` 仅镜像内采集（禁止 host 回退）；`atomic_persist` fsync + rename。
- **External blockers fix (2026-07-26):** PEP 427 wheel basename；deps `pip download`；persist 生命周期 + artifact 回滚；image-side `native_module_path`。
- **Persist/pip/blocked fix (2026-07-26):** identity 预计算路径 + 强制 rollback；钉扎 pip bootstrap（后被 layering 批细化 exit 语义）。
- **Bootstrap/blocked semantics fix (2026-07-26):** pip 引导 `PYTHONPATH` + `python -m pip`；Dockerfile 无浮动 syntax；identity `host_pip_version`。
- **BLOCKED layering fix (2026-07-26):** offline docker build → exit 1；deps/curl 曾一律 exit 3（后被 transport-aware 批收紧）。
- **Minor cleanup (2026-07-26):** 正式 gate 禁 `INJECT_TMP_RM_FAIL` 且先清扫再 95；success-path 父进程持有 `PHASE_EXIT_TMP`（不再 sed 日志）；`docker_build_offline` 更名；ledger 历史计数标注。
- **Transport-aware deps/curl classification fix (2026-07-26):** deps/curl 默认 exit 1；仅超时或 transport allowlist → exit 3；`deps-classify-regression`；正式 gate 禁 `INJECT_DEPS_TIMEOUT`。
- **HTTP status / docker pull local ref fix (2026-07-26):** curl `-w %{http_code}`；index 预检；pull stderr local allowlist；`deps-classify-regression` 扩展 503/404/pull 用例。
- **P0 curl_ec fetch wiring fix (2026-07-26):** `curl_fetch` stdout `ec\\thttp_code`；删 `PHASE_EXIT_LAST_CURL_EC`；pull allowlist 去掉 `manifest invalid`；回归含 `127.0.0.1:1` 真实 fetch。
- **Transport allowlist cleanup (2026-07-26):** 补 `Connection timed out` / `Read timed out`；去掉裸 `SSL:`；回归覆盖 conn-timeout、curl 28、ssl: token（已移除 pip NMD 误导路径）。
- **Package-level CDN deps wheelhouse fix (2026-07-26):** 删 PyPI 根预检与 `pip download`；`phase_exit_container_deps_wheels.py` lock 选 wheel + per-URL curl/sha256；`deps-classify-regression` 覆盖 deps-wheel 503/404 与 `select-regression`。
- **deps export/select wiring fix (2026-07-26):** `uv export --no-hashes --no-annotate` + `filter-export` + select 落盘/非空校验；跳过 win32 marker；`py2.py3-none-any`；`export-select-regression`。
- **curl transport + ABI wheel fix (2026-07-26):** curl ec **16/18/92/95/96** → exit 3；截断 `Content-Length` 活探针；平台轮 **`-tag-tag-`** 精确匹配（拒绝 `cp314t`）；`select-regression` cp314t-first fixture。
- **curl 97 proxy transport fix (2026-07-26):** transport allowlist 增加 **97**（proxy handshake → exit 3）；`deps-classify-regression` 合成回归覆盖。

---

## 11. Phase 1 九项退出条件（pre-commit 结论）

| # | 条件 | 结论 |
| ---: | --- | --- |
| 1 | PR-CORRECTNESS + PR-NATIVE @ exit commit | **部分** — 当前 dirty 快照通过；非 exact-commit |
| 2 | PHASE-EXIT-CONTAINER | **BLOCKED**（registry） |
| 3 | Required matrix PASSED | **是**（本快照 pytest） |
| 4 | Python/Rust vectors + Repository consumer | **是**（correctness gate） |
| 5 | Walking-skeleton artifact reopen | **是**（integration cell + PR-NATIVE） |
| 6 | `to_pylist()` demo 非 formal path | **是**（R4 已成立） |
| 7 | Blocking register 空 | **否** — §9 |
| 8 | Formal 规则写入 | **未在本轮变更** |
| 9 | Rust/wheel/container policy evidence | **部分** — wheel 模型已闭合；container 运行实证待 registry |

---

## WP5 R5 remediation update (2026-07-25)

- 实现审核修复：host wheel 唯一来源、compose 单镜像、负向 smoke 测试；见 §4 / §5 / §9。
- `bash vnext/scripts/gate.sh correctness` / `native`：remediation 后待重跑（见日志 `/tmp/wp5-r5-remediation-*.log`）。

---

## 12. Commit 后必须重跑（exact commit）

1. `bash vnext/scripts/gate.sh correctness`
2. `bash vnext/scripts/gate.sh native`
3. `bash vnext/scripts/gate.sh phase-exit-container`（需干净 worktree + registry）

---

## 13. Rollback

`git checkout b747590ac6ffdfe0e00b320363ce429e663e358e`

---

## 14. 未执行的外部动作

- **未** git commit / push / PR
- **未** 镜像 push 或 registry 发布
- **未** bless golden / normative vectors / scenario
