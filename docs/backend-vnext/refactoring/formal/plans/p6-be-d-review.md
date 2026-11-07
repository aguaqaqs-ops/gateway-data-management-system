# D BE-d 完整 tar：独立实施审核

2026-11-07。独审角色 `/root/be_d_review`，Owner 指定 GPT-6.1-Sol / max；实施为 `/root/be_d_impl`，协调为 `/root`。范围按 [D 工作单 §5](p6-be-d-work-order.md#5-启动收口) 包含 D 及既定联合最终验收准备收尾，不新建第三角色。

**当前状态：实施精确清单预检完成，无核心设计阻塞；未审产品候选，未作 D 或联合产品 GO。** 设计 GO、清单预检、06 定向结果、04/05 联合证据及 FE3 同制品互通分别记录。

## 1. 固定基线与权限

开始前已核 main 的 status/diff/recent log：clean，实际启动 HEAD `dfc8659744dbb9f763f77b74a3d7484cd9b67f18`；随后协调提交 `00f08cdcf2` 仅记录角色/状态，不回退 main。只读 detached 基线为 `/home/dev/gdds-reviews/p6-be-d-base-dfc8659744`，HEAD 固定为 dfc8659744，clean，`legacy` 指向主仓库本地参考目录。产品与后续修复仅在另建的固定 clean detached worktree 审核，不审 main dirty。

既有结论接缝：A1 已结束；V1 最终报告 `5dc01deeb543d4bdc07da02b0e0c6ba1f1472533` 的 §11 取代被暂停的旧 GO，保留最小绑定／scoped SQL→当前授权→完整 facts；V2 最终报告 `9ec62e82ad9b70776a03954c30edb94a29e1380a` 的 F1–F6 全关。D 的既有产品/容器基线为 `f8fb796f020ab47725359c176fc0e53bfb68aae6`，handoff 为 `3cd4400f9fe794c3126605ffd8abac7f81830b64`，`vnext` tree 为 `3860ed86194e4eafea9cfd408e7e7b5096b24bbb`。这些是既有审核引用，不是 D 的新验证结果。

已读 AGENTS、testing-conventions、比例化保障政策、ADR 0012、D 设计／工作单、联合 kickoff／准备工作单／协调交接、设计终审 §6，及 Comparison Bundle、artifact envelope ownership 与实际读取／保护接缝。按 ADR 0012 审协作 cleanup、正常 I/O、protected retention 和 root/symlink 边界；不重开已结束小节，不加入同 euid 对抗、helper/sidecar、持久下载或 evidence 状态机。

本角色只修改／显式暂存本报告，不改产品、tests、前端、实施 handoff、AGENTS、testing-conventions 或冻结基准。全部测试、编译、lint、容器和取证仅在规定的专用节点；本轮准备未执行这些工作，也未占用节点。普通 finding 直交原实施者，同一审核者复审。

## 2. 清单预检与唯一 owner 接缝

实施者须先提交 [D handoff](p6-be-d-handoff.md) 的精确字段、公开 port、错误和生命周期清单；以下是对已审设计的核收项，实际文件／nodeid 由该清单固定后填写，不把它们当作已实现事实。

| 不变量 | 本轮核收范围／权威验证 owner 的划分 |
| --- | --- |
| 当前授权先于 artifact | 两个公开 HTTP owner 参数化认证、permission、exact scope、readiness/TTL；沿用 V1 scoped 读取次序，不复制权限矩阵至编码或 Compose |
| manifest/closure/成员对应 | 生产 reader 先实际预检，准备对象再交 HTTP；原 metadata bytes 在前、最终 closure 按顺序每 entry 恰一个普通文件，同源同 hash 不同路径仍各发一次；reader owner 验拒绝缺失、损坏、重复／冲突／非法路径及非普通文件 |
| HTTP 错误／schema | Preview 缺失 `404 RESOURCE_NOT_FOUND`；History 缺失 `404 ARTIFACT_UNAVAILABLE`；完整性矛盾为 typed `503 BUNDLE_INTEGRITY_FAILURE`；公开 HTTP owner 核实际 status/body，schema owner 核生成的 OpenAPI：200 仅 `application/x-tar`、准确 length、quoted ETag 和安全 tar filename |
| encoder／长度 | 小型纯向量 owner 核 512-byte header/pad、PAX、end blocks 与实际 bytes，固定非业务 metadata；UTF-8 PAX 按整条 byte length 固定点，含 `12 path=中\n`、ASCII／中文／非 BMP／相邻记录／位数边界及畸形向量；不创建 Dolt |
| 生命周期／预算 | owning ArtifactStore 最小公开 port；单 stream 工作 buffer ≤1 MiB、活动 artifact handle ≤2，既有 16 MiB metadata 上界及保留对象计入内存说明；代表性正常、头前失败、流中 I/O、取消／断连和 cleanup 协作 owner 证明 close／保护释放，流中错误不得补假成功 |
| 生产接线 | 生产 wiring owner 覆盖 Preview MODIFIED_ONLY／FULL／replacement、History 两／三节点、shared、同源不同路径、异 schema、长路径及空表；其他层只做必要 smoke，不全靠 fake reader |
| 真实工具 | `real_dump_journey.py` owner 增加真实 FULL 输入入口，适配 `baseline_to_initial` 与 `initial_to_modified` 两 pair consumer，保留 V2 显式逐项 reason；完整读取两类 tar 并核全部 closure 路径／顺序／尺寸及相应逻辑／物理摘要，GET 完整读取时间／bytes 单列，不改 READY 锚 |
| FE3 互通 | 交生产 encoder 同字节 ASCII／中文／非 BMP tar、原 manifest／closure、长度／SHA、生成提交／命令／节点；前端修复提交及同制品解析／摘要／OPFS 证据由其 owner 提供，不把后端 GO 记为 FE3 依赖解除 |

逐项 Contract、公开 port/prepare result、metadata／stream／close 责任、错误映射、golden 与 test-owner 的实际变更清单待固定 handoff 到达后核收。发现 producer 不满足既有 Contract 时单独报告，不用下载去重、漏 member、链接、宽松 consumer 或重录业务 golden 掩盖。

### 2.1 固定清单 cf2091eadd 预检

固定 handoff 提交为 **`cf2091eadd4bb8e9a2122e4ed1b76ac8e7e83bbb`**，只读 detached WT `/home/dev/gdds-reviews/p6-be-d-list-cf2091eadd` clean／legacy 齐备。已核 `prepare_bundle -> PreparedBundleDownload` 的精确字段、错误矩阵、ASGI／iterator 双重幂等 close、64 KiB artifact chunks／2 FD、ustar/PAX 长度规则、实际产品文件和 owning 正文／golden 范围。

manifest 本身没有 closure 物理 ref；现有 `_digest.py` 的 semantic closure／manifest payload 和 `_assembly.py` 的 content identity 公式足以确定原 closure ref。清单要求只据此定位并核**原发布字节**，不把重新合成的 closure 当作下载文件，不改既有业务身份，方向成立。root 目录 FD 的共享 read-session 与 cleanup 排他非阻塞锁／锁内 eligibility 重查属于 ADR0012 协作生命周期控制；无新 durable 行、sidecar 或安全主体。

**清单预检通过，可按既定范围进入实现；这不是产品 GO。** 两项常规精度已直接交原实施者：PAX body 由整条路径构造时，其临时副本应明确计入 16 MiB metadata 预算或以有界片段编码，不能以发送切片代替工作 buffer 说明；生产 Preview／History wiring 行须补唯一实际测试文件名。二者不需要重开设计或新增路径限制，产品候选再核实际实现与计数。

## 3. 证据核收与联合收尾

06 仅按现场有效标志、clean 已提交 WT／legacy、离线缓存和实际脚本核定向证据；不把 V2 的 10:39:24Z 历史释放当作 D 可用预约。五包静态与 backend 扩展 build-input 均须核实际来源；非 serial 主体 `-n 4` 与 serial `-n 0` 分开，真空批 exit 5 只记 N/A。失败日志／SHA 保留，修复只补受影响范围，不机械重复完整 runner 或大向量。

既定收尾仍包括：固定联合最终候选和版本清单；04 受影响包权威（公共 fixtures 已变，预计六包实际运行）及必要当前 Compose；05 一次 fresh t1 合并 MODIFIED_ONLY／FULL、Submit／Review／Archive 与两类完整 tar；按实际影响核既有异常小型 wiring。日志需 hostname、起止 UTC／HEAD、exit／SHA、实际脚本和命令；镜像核 config digest＋全部 RootFS DiffID 及运行 provenance，跨节点不使用本机 inspect ID 代替 config digest。权威 runner 已覆盖的同提交 Compose 不重复。

D 局部代码／06 通过只作里程碑；联合最终证据另结论。DC33 最终真实范围仍待退出前 Owner 确认，不自动办理 exit、tag、push 或 S3。前端经 Owner 手动转发；确需前端判断的阻塞问题带具体场景／制品交协调，其余工作继续。

## 4. 当前容器决策

```text
Current reviewed HEAD: dfc8659744dbb9f763f77b74a3d7484cd9b67f18（准备基线）
Container rebuild required: no（本轮只读准备及本报告文档）
Last verified image revision: f8fb796f020ab47725359c176fc0e53bfb68aae6（引用 V2 §10）
Last verified RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Last verified backend/worker config: sha256:99188ad41cef18addc3e6760b45b7fd144a0e0f7fc6e51f0de137e7ac0bfc2b1 / sha256:7485e3f252d6cfd6ea4371a7f263913cdce2e392b8535e89369ed14dc312c028
Container gate for D: deferred（尚无产品候选／当前镜像）
Carried from: none（本轮未作 package/image carried）
Deferred gates: D 收敛候选的 06 最小生产 wiring／必要 Compose；联合最终 04 runner/Compose 与 05 fresh t1
Required execution point: 按已审工作单收敛后执行，精确 nodeid/命令由实施清单固定
```

本准备报告不新增测试通过声明，不取代固定产品审核和原始证据核收。
