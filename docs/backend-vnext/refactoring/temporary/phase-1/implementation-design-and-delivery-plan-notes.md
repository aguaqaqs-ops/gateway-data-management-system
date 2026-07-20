# Phase 1 WP0–WP2 Implementation Design Discussion Notes

状态：Resolved（2026-07-20；讨论与可行性证据）

适用阶段：Phase 1 — Executable Contracts and Walking Skeleton

正式实施计划：[`formal/plans/phase-1-implementation-design-and-delivery-plan.md`](../../formal/plans/phase-1-implementation-design-and-delivery-plan.md)

## 1. 本轮目标与边界

本轮把已经 Accepted 的 Phase 1 contract 进一步收敛为可直接交付的 WP0–WP2 implementation design。它不重新讨论 canonical encoding 的业务/byte 语义，也不实现代码、schema、vector、runner、Arrow kernel 或 PyO3 adapter。

本轮详细讨论：

- WP0：Rust workspace safety、architecture check 与可重复 gate。
- WP1：独立 Python Shared Kernel、JSON Schema 与 candidate-only vector tooling。
- WP2：独立 Rust Shared Kernel、首次 normative vector 发布与 Repository consumer。

WP3 Arrow/PyO3、WP4 Artifact 和 WP5 Harness 只作为后续依赖边界出现，不在本轮展开。

## 2. 仓库现状核对

讨论时的可验证现状：

- `vnext/backend` 与 `vnext/repository_service` 是两个独立 Python 3.14.6 `uv` project，各自持有 lockfile。
- `vnext/rust` 是 edition 2024 Cargo workspace，toolchain 固定为 stable Rust 1.97.0。
- Rust workspace 只有 `gateway-compute-core` 与 `gateway-compute-python`；尚无 Shared Kernel crate。
- Python 侧尚无独立 Shared Kernel project，也没有 `vnext/fixtures/`、vector schema或static normative vector root。
- 当前 Rust demo 仅处理 nullable `int64` doubling；adapter 使用 `to_pylist()`，只能作为 bootstrap evidence，不能成为 formal Arrow/PyO3 path。
- 当前没有 repository-level task runner或provider-specific CI workflow；因此 Phase 1 gate需要一个最小、CI-ready、供应商无关的入口。
- `gateway-compute-core` crate root已经有 `#![forbid(unsafe_code)]`，但 workspace 尚未统一继承 Rust/Clippy lint policy。

未发现需要重新打开 Phase 0 业务语义的 formal 内部冲突。

## 3. 已接受的关键决定

### R21. 双独立 Shared Kernel 包

接受：

```text
vnext/shared_kernel                  Python project
vnext/rust/gateway-shared-kernel     Rust workspace member
```

Python distribution 名为 `gateway-shared-kernel`，import package 为 `gateway_shared_kernel`；Rust package 名为 `gateway-shared-kernel`，library crate 为 `gateway_shared_kernel`。

两者共享 formal contract、schema和static vectors，不共享算法代码，也不通过FFI互相调用。这样可以保持语言实现独立，并允许 Repository Service复用Python package而不复制第三套算法。

### R22. JCS 使用独立库加项目级严格封装

接受：

- Python 使用固定版本 `rfc8785`。
- Rust 使用固定版本 `serde_json_canonicalizer`。
- 两边分别实现输入层的 UTF-8、duplicate member、I-JSON number、Unicode/noncharacter和stable error classification。

不选择双语言完全手写JCS，也不vendor单一语言reference implementation。第三方库只负责RFC 8785 serialization，不能拥有本项目stable error code。

### R23. WP1 只处理 canonical executable contract

接受：WP1只建立canonical vector schema、Python reference和candidate tooling。Scenario YAML、golden envelope、runner/harness schema延至WP5，不为了提前“完成目录”而引入YAML parser或空harness abstraction。

### R24. WP1 candidate、WP2首次发布

WP1只生成out-of-tree candidate；在Rust独立实现、人工byte review和Repository consumer均通过后，WP2才把同一closure作为普通reviewed patch发布到固定normative root。普通CI永不生成或bless vectors。

### R25. Compute core 延迟接入

`gateway-compute-core`在WP0–WP2不依赖新Rust Shared Kernel。到WP3真正实现`canonical_row_hashes_v1`时再建立依赖，避免unused dependency和提前冻结Arrow mapping内部结构。

### R26. 测试也不建立panic lint例外

WP0–WP2所有Rust target统一拒绝`unwrap/expect/panic/todo/unimplemented`。Cross-stage policy允许未来为test readability建立显式test-only exception，但本轮没有需要，不预建waiver机制。

## 4. 依赖可行性证据

### 4.1 Python

- `rfc8785==0.1.4` 与 Python 3.14.6 可安装和运行；用于canonical serialization。
- `jsonschema==4.26.0` 支持Draft 2020-12和Python 3.14；只放入`conformance` optional extra/dev test path。
- Python标准库JSON parser必须用duplicate-preserving hook并拒绝NaN/Infinity；不能把普通`json.loads()`默认行为当作strict parser。

### 4.2 Rust

- `serde_json_canonicalizer==0.3.2`提供RFC 8785 serialization；项目仍需recursive visitor检测duplicate member和执行I-JSON约束。
- `serde`、`serde_json`、`sha2`与现有`thiserror`足以实现production core。
- `base64`只服务vector integration test，不进入production API。
- 不使用`rust_decimal`：它不能表达MySQL最多65位precision；decimal改为ASCII lexical normalization。
- 不需要temporal crate：v1只需确定性的Gregorian/component validation，避免locale、timezone和tzdb依赖。

所有实际版本在实现时精确pin进manifest与lockfile；dependency review记录safe API边界、build/proc-macro/native行为和回退方案。

## 5. 类型范围澄清

Formal原文中的“owner-supported MySQL range”需要在实现前成为机器规则，但不改变既有语义：

- Decimal precision：`1..=65`。
- Decimal scale：`0..=30`且`scale <= precision`。
- `BIT(n)`：`1..=64`。
- Signed/unsigned integer width：`8 | 16 | 24 | 32 | 64`。

这些范围由Shared Canonical Encoding contract拥有，并在test-only vector schema中镜像校验。Canonical Row Hash Arrow mapping可支持更宽的Arrow decimal物理能力，但不得扩大当前owner-declared logical range。

## 6. Candidate 与 normative 发布流程

固定流程：

```text
hand-authored case definitions
  -> Python writes new empty candidate directory
  -> schema/closure validation
  -> Python full conformance
  -> independent Rust full conformance
  -> human bytes/classification review
  -> reviewed patch to fixed normative root
  -> Python/Rust/Repository read-only gates
```

Candidate generator必须拒绝normative root、symlink/path escape、existing non-empty output和任何overwrite；不提供`--bless`。`vector-set.json`在四个已排序JCS JSONL文件之后生成，以其raw hash/count/size建立closure。

## 7. Delivery 切分

- D0：本讨论记录、正式implementation plan、导航和owner范围澄清。
- D1/WP0：安全、构建与architecture gate，可独立合入。
- D2/WP1：Python reference、schemas和candidate tooling；明确标记尚未发布normative closure。
- D3/WP2：Rust reference、Repository consumer及首次normative closure发布。

D3通过只是Phase 1 canonical executable-contract checkpoint，不等于Phase 1 exit；Arrow/PyO3、Artifact、Harness、真实data scenario和container evidence仍需后续WP完成。

## 8. Formalization mapping

| Discussion item | Formal owner / destination |
| --- | --- |
| R21、R25 package/crate topology | Phase 1 Implementation Design and Delivery Plan |
| R22 JCS implementation strategy | Phase 1 Implementation Design and Delivery Plan；byte semantics仍见Shared Canonical Encoding |
| R23 WP1 scope | Phase 1 Implementation Design and Delivery Plan |
| R24 candidate/publication lifecycle | Canonical Encoding Normative Vector Schema + Phase 1 Implementation Plan |
| R26 workspace/test lint decision | Rust Safety and Performance Policy + Phase 1 Implementation Plan |
| Decimal/BIT/integer range | Shared Canonical Encoding + Canonical Encoding Normative Vector Schema |
| D0–D3 sequencing and gates | Phase 1 Implementation Design and Delivery Plan |

本文件仅保存讨论和可行性证据。若与Accepted owner contract冲突，以owner contract为准。
