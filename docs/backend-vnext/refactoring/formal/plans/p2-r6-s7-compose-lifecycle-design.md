# P2-R6-S7 Compose Lifecycle Design

状态：Design baseline frozen by discussion; independent review required before implementation

日期：2026-08-16

适用范围：`P2-R6-S7` Compose harness、remote client、restart/replay 与
fresh/restart/restored lifecycle。本文不重新拥有 Repository Service public Contract、S4
snapshot semantics 或 P2-R6 final gate；冲突时回到对应 formal owner。

## 1. Authority and entry

权威顺序：

1. [Repository Service Contract](../contracts/repository-service.md) §§14–18；
2. [P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md)；
3. [P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md) §§7–10；
4. [P2-R5 Commit-pinned Read Execution Plan](p2-r5-commit-pinned-read-execution-plan.md)；
5. [P2-R6-S4 Staged Execution Guide](../../temporary/phase-2/p2-r6-s4-staged-execution-guide.md)；
6. [Testing Conventions](../../../testing-conventions.md) and repository `AGENTS.md`。

S7 的入口是 Stage K handoff commit `0b4969fe`。生产 image 的最近验证代码身份单独为
`656a66bf`，image ID 为
`sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296`。S7 的 Compose/test harness
变更完成后必须生成新的 provisional candidate/image；Stage J image 只能作为祖先回归证据。

## 2. Goal and non-goals

### 2.1 Goal

在当前 provisional candidate 上建立可审计的 Compose lifecycle evidence，覆盖：

- R4 import restart/replay；
- R5 inside-network commit-pinned read；
- R5 gate-host commit-pinned read；
- fresh、restart、restored whole-root lifecycle；
- 每个 nodeid 的 process/thread/query-temp/container/network/volume cleanup；
- client、service、image、fixture、public facts 与 candidate SHA 的 provenance 绑定。

S7 通过后只表示 deferred Compose/lifecycle inventory 已在当前 provisional candidate 上
收集并通过；不表示 S8/S9/S10 或 `phase_2_complete` 通过。

### 2.2 Explicit non-goals

- 不发布 Repository Service host port；
- 不让 Service 依赖 Client，或增加常驻 client/snapshot service；
- 不修改 public route、DTO、Contract、auth、snapshot/restore 语义或数据格式；
- 不引入 production client dependency、sidecar、broker、socket、独立 UID 或新 daemon；
- 不把 Stage J image、S4 TestClient evidence 或 S6 HTTP evidence 当成 S7 container PASS；
- 不在 S7 执行 W1/W2、Candidate A v8 formal 或 Phase 2 final gate；
- 不承诺跨灾难 RPO/RTO、CommitId 跨版本稳定或 online snapshot。

## 3. Confirmed decisions

### 3.1 Compose topology

| path | topology | boundary |
| --- | --- | --- |
| Service | `repository-service` in existing `p2-r2` profile | internal network only; no host port |
| inside-network client | ephemeral one-shot client container attached to the Compose network | exits after one consumer run |
| gate-host client | ephemeral client process/container reaches the service through dynamically discovered Linux bridge address | address recorded in evidence; no production port publication |
| snapshot operator | transient helper/CLI using the same candidate image and `gateway` euid | no resident service or socket |

The client test environment is built from the same S7 source candidate with the locked
`repository_client` project and `versioned_v1` fixtures. It is a test-only image/process and is
not added to production Compose. The service image remains the production runtime image under test.

### 3.2 Fixture and public oracle

The authoritative read oracle is the existing contract-owned fixture consumer:

```text
vnext/repository_client/tests/support/versioned_fixture_consumer.py
vnext/repository_client/tests/fixtures/versioned_v1/
```

The consumer creates one repository and publishes two immutable commits:

```text
c0 = initial commit returned by create_repository
c1 = import of versioned_v1/c1
c2 = import of versioned_v1/c2
main = c2
```

It reads both `c1` and `c2`, checking catalog and row facts without depending on Arrow batch or
row order. The fixed expected package facts and manifest digests remain the test oracle. S7 must
not replace this with raw SQL, direct SQLite/Dolt reads, or the five R6 external business fixtures.

### 3.3 Lifecycle semantics

| state | required operation | expected fact |
| --- | --- | --- |
| fresh | new Compose project and new empty named volume | service becomes ready; c0/c1/c2 flow succeeds |
| restart | stop service, then `up -d --no-build --force-recreate` using the same named volume | service becomes ready; previously published public facts remain readable |
| restored | stop service, whole-root snapshot, mutate source, prove a different empty target, restore whole root, run `check`, start same image | snapshot-time c1/c2 facts remain; post-snapshot mutation is absent |
| teardown | stop/remove service and ephemeral helpers; `down -v --remove-orphans` | zero containers, networks, volumes, service children, query temps and test roots |

`docker compose restart` alone is insufficient for the restart gate because it does not prove
container recreation and startup from the same durable volume. A fresh project/volume and a restored
project/volume must never share writable state.

### 3.4 Snapshot boundary

S7 reuses S4's private whole-root protocol:

1. Service is stopped and the `hold` helper obtains the durable-root lock;
2. ready JSON is complete and the helper remains alive;
3. the whole mounted data root is copied once;
4. hold exits cleanly and releases the lock;
5. restore target is proved empty before any copy;
6. the entire root is restored, ownership is corrected, and `check` runs while Service is stopped;
7. the same image starts against the restored root and public HTTP facts are replayed.

Partial component, SQLite-only, single-Dolt-tree, non-empty overlay and live-root procedures must
fail closed. S7 does not add a second restore implementation or a persistent snapshot manifest.

## 4. Nodeid and evidence ownership

S7 owns four exact Compose nodeids. Each nodeid has one behavioral owner and one cleanup inventory;
the aggregate report may summarize them but cannot replace per-node evidence.

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
```

### 4.1 Import restart/replay owner

The existing R4 test remains the owner of import upload → submit → restart/replay → operation and
main/ref result. It must run on the S7 provisional image and prove no duplicate publication,
unexpected operation transition, private ref leak or volume corruption after restart.

### 4.2 Inside/gate-host read owners

Both read nodeids run the same contract-owned consumer and expected facts. They differ only in
network boundary and client placement. Each must prove:

- bearer authentication and readiness;
- c1 and c2 catalog/rows by immutable CommitId;
- `main` resolves to c2;
- c1 remains readable after c2 publication;
- moving `main` does not change a pinned c1 read;
- Arrow stream closes with EOS on success and leaves no client/service child or temp residual.

### 4.3 Restored lifecycle owner

The fourth nodeid owns fresh/restart/restored sequence, snapshot public facts, post-snapshot
mutation absence, `hold/check` result, same-image startup, and final cleanup. It must not hide
restore assertions inside the gate-host read test.

## 5. Harness architecture

### 5.1 Project and resource identity

- Every nodeid generates a unique project name with a stable test prefix and random suffix.
- Every nodeid uses its own token file, project, volume and temporary result directory.
- Cleanup is in a `finally` path and is also asserted after expected failures.
- Inventory uses Docker labels and explicit `ps -aq`/network/volume queries; no broad host-wide
  deletion is allowed.
- Evidence records project name, image ID, source/candidate labels, network/volume identifiers in
  internal evidence only; external summaries redact host paths and secrets.

### 5.2 Client process

The ephemeral client image/process is built from the same source candidate and locked
`repository_client` environment. It mounts only read-only fixture/runner material and receives the
base URL, bearer token, and fixture root through environment variables. It must not receive the
service durable root, Docker socket, host root or raw secret values in logs.

The client exits with a typed summary containing only `status`, repository ID, c0/c1/c2 and main
commit. The harness captures stderr separately, redacts bearer material, and fails if stdout has
extra fields or raw paths.

### 5.3 Service image and provenance

Formal S7 evidence binds:

```yaml
candidate_sha: <S7 provisional candidate>
container_validated_code_sha: <same candidate>
build_input_revision: <effective build input>
source_tree_sha256: <effective source digest>
service_image_id: sha256:<64 hex>
client_image_id: sha256:<64 hex or explicit host-runner identity>
service_uv_lock_sha256: <repository_service lock identity>
client_uv_lock_sha256: <repository_client lock identity>
```

If Compose, harness, Dockerfile, dependency or runtime wiring changes, the affected candidate must
be rebuilt before the associated gate is called PASS. An old image may be used only for smoke or
comparison and must be labeled ancestor evidence.

## 6. Failure and consistency contract

The following conditions are S7 failures, not warnings:

- missing or skipped exact nodeid;
- service not ready, auth mismatch, wrong network reachability or accidental host-port exposure;
- c1/c2 catalog, row, CommitId or main-ref mismatch;
- restored root includes post-snapshot mutation;
- restore check runs while Service is live or target was not proved empty;
- image label/source/candidate mismatch;
- any process, thread, Dolt child, query temp, container, network, volume or work-root residual;
- cleanup failure after an expected negative probe;
- evidence omits the command, candidate/image identity, result or cleanup inventory.

A failed nodeid returns to its owning implementation step. The review step never edits production or
test code and never converts a missing gate into a pass.

## 7. Acceptance matrix

| invariant | required proof | owner |
| --- | --- | --- |
| no public host port | rendered Compose config and negative reachability check | S7-B/S7-E |
| one-shot client only | client container exits and no resident client service exists | S7-B |
| commit pin | c1 read after c2/main publication equals c1 oracle | read nodeids |
| restart durability | force-recreate same volume, ready, c1/c2 facts preserved | import/read/lifecycle nodeids |
| restore isolation | post-snapshot mutation absent after whole-root restore | lifecycle nodeid |
| snapshot safety | hold/check ordering, empty target and same-image startup | lifecycle nodeid |
| failure cleanup | zero process/thread/temp/container/network/volume residual | every nodeid |
| provenance | service/client image identity and candidate labels match | S7-E |

S7 exit requires all four nodeids green on one provisional candidate, independent review with zero
blockers, full cleanup inventory, and a handoff that declares S8 as next stage. It does not close
S8/S9/S10 or set `phase_2_complete: yes`.

## 8. Reopen conditions and assumptions

Reopen S7 design review if any of the following changes: public host-port exposure, client becoming
a production dependency, a second service/helper identity, a different restore unit, a different
CommitId/read oracle, a multi-node/shared writable root, or a need for cross-version restore.

Current bounded assumptions, checked in S7-A rather than treated as design facts:

- the Stage J remote builder/retained dependency cache and Linux gate host are available;
- Docker Compose can discover the service network bridge address on the gate host;
- the same candidate can build the transient client runner without adding a production dependency;
- the S4 private snapshot CLI and its focused/integration tests remain green.

## 9. Design verdict

```yaml
design_status: ready_for_independent_review
public_contract_changed: no
topology_changed: no
restore_semantics_changed: no
fixture_oracle: repository_client.versioned_v1.c0_c1_c2
nodeid_count: 4
container_trigger: yes
phase_2_complete: no
next: P2-R6-S7 execution plan
```
