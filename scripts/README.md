# 后端阶段门禁

`scripts/run-stage-gate.py <full-sha> [--packages shared_kernel,...] [--session name]`
只在开发节点编排，经 BatchMode SSH 在 `ct108-gw-dms-04` 执行；worker 严格校验实际 hostname 为 `gw-dms-test-04`，错误节点在占用前以 exit 2 拒绝。工具自身须已提交，目标完整 SHA
须先通过获准 LAN 传到 04 的 `/home/dev/gateway-data-management-system`。首次自动创建固定 detached
worktree `/home/dev/gdds-stage-gate` 和相邻归属记录；已有树若无归属记录、dirty、attached 或 legacy
类型/目标错误，均拒绝接管。不要手工创建固定树或删除归属记录。

`--purpose stage`（默认）或 `s3-ready` 可按闭包查表。`--fresh`、`--purpose s5|release|production`
始终完整六包，跳过查表并在当前 SHA 构建 RS；backend/worker 仍由权威 runner 内的 Compose harness
构建。项目最终验收必须选对应 purpose，不能用普通 stage 结果替代。前端和真实数据仍使用既有入口。

04 的可选节点配置 `/home/dev/gdds-stage-gate-config.json` 由节点维护者提供；运行容器包时必须有
cache_provenance 和预置依赖设置。配置不在 Git 内，不允许更换 runner、closure、uv wrapper 或注入
任意命令，不继承调用者的代理/index/runner 覆盖。最小容器示例（将占位值替换为本节点已核实的来源）：

```json
{
  "environment": {
    "GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES": "1",
    "GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE": "gateway-backend-deps:lock-<actual>",
    "GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES": "1",
    "GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE": "gateway-p2r1-repository:lock-<actual>",
    "GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE": "gateway-repository-client-e2e-base:local"
  },
  "cache_provenance": {
    "source_node": "CT201",
    "source_commit": "<full-sha>",
    "artifact_sha256": "<archive-or-cache-digest>",
    "prefilled_at": "<UTC>",
    "endpoint_identifier": "<approved-LAN-cache-or-local-preload>",
    "identity_record": {
      "path": "/home/dev/<record-with-config-digest-and-all-RootFS-DiffID>.json",
      "sha256": "<record-sha256>"
    }
  }
}
```

也可配置 `GATEWAY_P2R1_CACHE_URL`、`GATEWAY_REPOSITORY_SERVICE_IMAGE`、
`GATEWAY_REPOSITORY_BASE_IMAGE`、`GATEWAY_TEST_WORKERS`、`CARGO_BUILD_JOBS`；完整允许集见脚本
`ENV_KEYS`。URL 禁止携带凭据，cache provenance 不记录 secret；上述五项来源字段必填，来源提交/制品摘要/UTC 格式校验，identity_record 须存在且 SHA256 匹配。缺缓存停止；准备后新开 run，不能覆盖失败。
`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、固定 TMPDIR、Cargo PATH、build network none 不可覆盖。

每次运行写 `/home/dev/gdds-gate-results/<full-sha>/<run-id>/result.json`，同目录保存原始日志、其 SHA256、
准备及 runner 实际起始 manifest、Compose provenance。JSON 用原子 rename；失败不更新成功来源。
原始成功来源必须同节点、同固定树、同脚本 SHA、clean、起止 HEAD 一致、整体 runner exit 0、包通过，
且原日志/manifest 摘要相符。carried 直接指原始实跑，不递归解析 carried。修改脚本一律保守失效旧表。

容器 carried 另核 RS build-input/source-tree labels，backend 同源闭包覆盖 backend/worker；区间逐提交扫描
`vnext/`（含完整分支历史和 merge 对每个 parent 的 diff），任何修改（含改后改回）保守触发容器包重跑。这个首版允许额外重跑，避免漏判 runtime/harness
边界。容器结果的 `images` 记录 RS 身份，backend/worker 实跑身份从同目录 Compose provenance 引用。
占用冲突 exit 3，不等待或接管。捕获信号后先停止本人子进程，再核现场、写结果和释放本人标记；无法确认
收尾则保留标记。SSH 中断或 SIGKILL/断电时，协调者核远端进程/结果/标记后处理，不直接删除标记。

窄自测：在专用节点取得占用、clean 已提交 checkout 上运行
`python3 -m unittest discover -s scripts/tests -v`。替身只替换平台准备和 runner 可执行文件，验证失败、
信号、冲突、查表、原件损坏和容器身份；不能代替至少一次真实权威 runner 成功及文档提交命中。
