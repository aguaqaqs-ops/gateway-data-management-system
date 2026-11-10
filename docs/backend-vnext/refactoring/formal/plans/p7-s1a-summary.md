# P7 S1a 实现与验收总结

> 本页记录已完成的产品候选 V 验证。文档 H 的同04固定树闭包/容器绑定、最终独审与外部 EXIT_GO 是退出前置，本页不代替该签署；历史 A 稿保持当时事实。

全S1a审核起点 S=`5ddd73b962e2432f961a46f6743395a53a388435`（vnext等于P6退出B），G实施基线为 `80ea194300fdb209e7deaf937d55584bc5f64699`；产品门禁 V=`1736dcf64776cc216add599fb25a94a061c7784b`。一组一worker、W=K=1，十个storage slot显式配置；backend/RS预检实际mount/marker/权限/cgroup，位置codec统一四字段ArtifactRef，生产scratch/staging显式owner与有界写入，保护/发布/borrow/cleanup事务与完整性闭合。容量按目标FS校验watermark+已知headroom，同FS合并需求，source已落盘不重复扣；低水位拒绝为既有503 SERVICE_NOT_READY/capacity_rejected，producer超限仍413。

| 证据 | 实际来源与结论 |
|---|---|
| 04权威六包/容器 | V，run `20261110T171630Z-76767a78c862`，六包全部实际run、container run，stage/runner均exit0，clean起止同V，occupancy released；原件身份如下。86daa测试失败及8cb外层provenance路径失败保全，不作carried来源。 |
| 05无shim产品真实链 | `8cb31da5` clean，t1 v1/v2 MODIFIED_ONLY首次/重复，上传→Preview→Submit/Review/Archive→四完整下载；不同真实filesystem功能配置，`real-r4/journey.log` SHA `6ea06690…` exit0 |
| 保护后清理 | 420 unique实际保护refs前后readback SHA相同，31次生产bounded CLI删明确过期无保护probe，四tar完整复读SHA不变；`real-r4/postflight.log` SHA `912646c6…` exit0 |
| 可见集合比较 | 固定P6 `p6-exit`与8cb，在Owner批准局部一次UUID fixture、相同repository/History业务身份下实际生成四tar，literal路径集合354/105/111/114和递归manifest字段集相等；规范化OpenAPI同SHA `4c2ddca7…`；业务golden相等 |
| 最终focused | 8cb BE457/RS56/ordered Compose1通过；1736工具15、闭包/runner65通过，覆盖纯输出路径、有效/未知输入敏感性、mixed carried的custom tag/label变化拒绝及RS精确根tool输入闭环 |

04原件目录：`/home/dev/gdds-gate-results/1736dcf64776cc216add599fb25a94a061c7784b/20261110T171630Z-76767a78c862/`。`result.json` SHA `abb7f441ad7dd3a0857a8b6252c7c9bd6e816b6f9d8915aab7b3f8927a9aed15`；`runner.log` SHA `e8ecb693ff0eaa9fe7b09bb20d297e43c0dfb47e6581ba553d71342f872e393e`；`compose-provenance.json` SHA `b667ceda15297b351698540b228ce58c0814c3e16be9c05f380fc9c12e42d84b`。

04产品真OCI config与完整有序DiffID原件位于04 `/home/dev/gdds-test-tmp/p7-s1a-product-identity-1736/`，取证日志 `/home/dev/gdds-stage-exchange/p7-s1a/gate/product-identity-1736.log` SHA `4af766a41b696a9c13796ec55a2ea5d0bf32b7d428803eee77e48a2cd91d8ec8`；本机inspect Id与config digest分列。

标准输入SHA：v1 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`，v2 `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`。未扩大t4/FULL/多设备容量。05真实分FS为持久ext4上的keeper overlay与其余ext4，实际原子发布/flock/fsync/bind/marker/euid、stop/start保留及fresh预检成立；底层同一ext4，不称独立物理盘、故障域、容量相加或断电持久。小卷实际ENOSPC与产品marker失效→latched拒绝→重启恢复为明确86daa来源故障回归，相关实现至8cb不变，不冒称新SHA fresh。

保留fresh旅程的字面差异与失败比较；固定身份补充不是无shim门禁。逐项2575 ID/digest变化包含location codec、新ref元数据raw SHA/size、v2/History surface/bundle integrity传递，以及History实际submission role变化；未改写tar/模板归一化，未删repo绑定或完整性preimage。canonical_state、identity评估、Preview计数和History12 records保持相等。终态420refs实际owner种类无活跃T1/Submission，移交证据另见owner测试及实际中间业务链。

全部原输入、tar/API、比较原件、失败、镜像本机Id/真OCIconfig/完整DiffID、缓存来源与UNKNOWN项、原运行logs/SHA见外部 `/home/dev/gdds-stage-exchange/p7-s1a/g/handoff.md` 及 `g/evidence/evidence-index.json`；原件05 `/home/dev/gdds-test-tmp/p7-s1a-g/` 保留。8cb→V仅门禁/闭包工具、README及测试，真实链仍标8cb语义证据，当前V容器证据为上述04实际重建/运行。05隔离数据已逐文件SHA/权限/属主核档，keeper/小卷移除，05占用释放；不push/上线、不启动S1b。

下一步按 [S1a 前端/BE-b 交接](p7-s1a-frontend-beb-handoff.md)：仅在 S1a 本地 exit 并合 main 后，由后端设计会话开始 BE-b 第二步设计，随后实施，前端设计会话参与审核；不提前实施 BE-b，不push/上线、不启动S1b。DC74未生效，随P6退出关闭，历史草案不作为额外门禁或下载性能要求。
