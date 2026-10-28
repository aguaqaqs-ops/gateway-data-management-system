# Bundle Assembly Capability

本文定义并记录 comparison bundle v3 的实现。Contract 见 `../contracts/comparison-bundle.md`。

Bundle assembly 是 flow-neutral capability。它把一个或多个 `ComparisonSurface` 及其 artifacts 闭合为可交付 bundle root 或 bundle artifact；flow 可以在外层加 preview/history/archive envelope，但 bundle core 不理解业务状态机。

前后端简化策略见 `../frontend-surface-simplification.md`。本 capability 只负责 bundle core，不承载兼容层输出。

## 设计原则

规则：

- Flow 负责决定是否需要下载包、TTL、权限和 envelope。
- Operation 负责调用 capability 并在 READY 前完成 artifact closure。
- Bundle assembly 负责校验并重写 refs、复制 artifacts、写 manifest/closure、计算 bundle digest。
- Bundle assembly 不计算 comparison、risk 或 surface。
- Bundle assembly 不读取 SourcePackage、RepositoryRef 或 repository server。
- Bundle assembly 不依赖旧 preview/workbench/history modules。

## 初步迁移策略

本 capability 的第一步先把 `ComparisonBundle` core 从旧实现里独立出来，当前轮只做 vNext core，不把 preview/workbench 兼容形状当成通用 bundle 事实：

- 新实现落点为 `vnext/backend/src/gateway_backend/capabilities/bundle_assembly/`。
- 旧 preview / workbench 兼容层不在 core 内默认实现，也不作为 bundle truth。
- 当前轮优先实现 manifest、artifact closure、bundle-relative ref rewrite、bundle digest 和 pair 组织。
- 在 core 稳定前，不把旧 preview 入口转发到新实现，也不反过来依赖旧 preview 形状。

这样做的目标是让 bundle core 先独立收敛，兼容输出如需保留由 flows / operations 在上层 materialize。

## 旧实现参考边界

可参考：

- History compare bundle 的 2/3 节点 pair 组织方式。
- Preview bundle builder 的 bundle-relative path 和 artifact layout 经验。
- 同一 input snapshot artifact 在多 pair 中只导出一次的优化。

不直接继承：

- `preview-bundle/v2` 作为通用 bundle core。
- preview token、revision、strategy manifest、submit binding。
- 旧 bundle builder 中的 diff/risk/surface 计算逻辑。

## 能力列表

```text
bundle_assembly
bundle_manifest_writer
bundle_ref_rewrite
bundle_artifact_closure
flow_envelope_writer optional
bundle_cache optional future
```

## 建议代码模块

建议落点：

```text
gateway-data-management-system/backend/backend_vnext/capabilities/bundle_assembly/
```

内部拆分：

```text
models.py
assembler.py
layout.py
ref_rewrite.py
manifest.py
digest.py
versions.py
```

依赖方向：

```text
bundle_assembly
  -> surface_assembly public API/contracts
  -> artifacts
  -> shared kernel
```

禁止依赖 comparison compute、risk evaluation、repository_server、flow、operation runtime 或旧业务模块。

## 输入输出

输入：

```text
BundleAssemblyInput:
  bundle_profile
  inputs
  pairs:
    - surface_result: SurfaceAssemblyResult
      surface_artifact_closure: BundleArtifactClosure
  shared_artifacts optional
  artifact_policy
  bundle_contract_version
```

输出：

```text
BundleAssemblyResult:
  bundle_manifest
  bundle_digest
  bundle_artifact_ref
  artifact_closure_manifest
  diagnostics
```

规则：

- 每个 `surface_result` 必须为 `READY` 且通过 Surface validation；`CANCELLED` 直接使 bundle `CANCELLED`。
- required pair 失败使 bundle `FAILED`；optional pair 失败不带入 partial artifacts，整体为 closure-valid `DEGRADED`。
- 每个 surface ref 必须在 pair/shared closure binding 中出现；closure 中嵌入的 JSON ArtifactRef 也必须声明并可回放。
- business projection 声明的 supplemental artifacts 必须按 pair-relative ref 写入，并在 closure 中记录 ref、kind 与 content digest。
- `bundle_artifact_ref` 是内部 artifact ref，不是 host path 或 download URL。

## Layout 与 Ref Rewrite

Bundle assembly 把 operation-local 或 cache-restored refs 重写为 bundle-relative refs。

规则：

- 仅复制同一 artifact bytes 时，surface digest 不变；若 JSON closure 因嵌套 ref rewrite 产生新的 content/manifest integrity，Bundle 重新封存最终 surface digest。
- 所有 bundle-relative refs 必须被 closure manifest 覆盖。
- 如果 artifact policy 使用 hardlink，manifest 仍按 bundle-relative layout 表达。
- 如果目标 storage 不支持目录语义，layout 可以由 manifest 映射实现。
- `ArtifactRef` 不编码 filesystem path；bundle-relative logical path 只存在于 manifest/closure。
- manifest/closure 各自受 16 MiB cap 约束；所有 bytes 写入并回读验证后才越过 publication boundary。

第一版建议 layout 见 `../contracts/comparison-bundle.md`。

## 多 Pair

第一版支持：

```text
SINGLE_PAIR
MULTI_PAIR
```

规则：

- 每个 pair surface 独立闭合。
- Pair 之间默认不合并 records 或 risk artifacts；但当 MULTI_PAIR 闭包出现相同 `source_ref` 且相同
  kind 的重复 binding 时，assembler 提升为 `shared/{kind-segment}/...`（详见
  `../contracts/comparison-bundle.md` 跨 pair 共享规则）。合法 bundle（无重复 ref）不受影响。
- Shared snapshot/input artifacts 可以只写一次。
- composite points/formulas supplemental artifacts 保持 pair 隔离；Dataset Replacement 的 before/current side artifact 也不得合并。
- 3 节点 history compare 使用两个 pair，不生成三方 diff。

## Flow Envelope Writer

Flow envelope writer 是可选薄层，可由 flow 自己实现，也可复用 bundle assembly 的 helper。

规则：

- Envelope 引用 `bundle_digest` 和 `bundle_artifact_ref`。
- Envelope 可以包含 operation id、download metadata、权限和 TTL。
- Envelope 不写入 surface core。
- Envelope 不改变 bundle digest。

## Cache 接入点

第一版不实现正式 bundle cache。

未来可选：

```text
flow_assembly_cache
```

规则：

- Flow assembly cache 可以缓存 envelope + bundle artifact，但不是 comparison fact。
- Cache restore 后仍必须校验 bundle artifact closure。

## Ordered Table 第一版策略

Bundle assembly 不理解 ordered semantic，只负责闭合 artifacts。

第一版：

- ordered unsupported 表按普通 degraded surface 闭合。
- 不生成 ordered-specific navigation。
- 不要求 ordered records artifact。

后续 ordered diff compute 完成后补充：

- ordered records artifact closure。
- ordered interval/move navigation projection。
- ordered risk annotations 的定位文件。

## 测试与验收

Unit：

- bundle-relative ref rewrite。
- closure manifest 校验。
- bundle digest 稳定。
- forbidden host/cache ref rejection。

Contract：

- 单 pair bundle。
- 两 pair history-style bundle。
- shared input artifact 只引用一次。

Integration：

- `SurfaceAssemblyResult -> BundleAssemblyResult`。
- cache-restored records/risk artifacts -> bundle-relative closure。
- ordered unsupported surface -> bundle READY。

## v3 实现状态

- public contract version：`backend-vnext/comparison-bundle/v3`。
- public entrypoints：`assemble_bundle`、`validate_bundle`、bundle digest/ref helpers。
- Bundle 只允许使用 Surface public API/contracts、artifact port 和 shared kernel；不导入 comparison、risk、Repository、flow 或 runtime。
- Bundle cache、GC/retention、flow envelope、Docker/Compose、Rust 和 runtime integration 仍 deferred。
