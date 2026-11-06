# Phase 6 JCS 候选镜像验证与单步真实输入诊断

状态：2026-11-06，DC80 接续设计，待范围审核。先准备候选镜像和限定容器验证，不重跑合成 closure；真实输入运行仍须完整候选专属一次 GO。

## 1. 目的与证据边界

产品候选固定 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，是冻结 e798 加 RS 修正 4497 和已审 JCS sink 改动；交接 `172d53cfeb`，代码/局部语义审核 `b37041df2f` §42。五包静态及 191 项 focused 已有合格来源，不再重复。JCS 改动仅去掉整块输出聚合，未证明现场 lease 已修复。

完整 closure 合成诊断已按 290 秒停止，审核者已读取 supervisor 和原始 checkpoint：两次 change-set digest 完成，第三次 payload 完成，25 次续租成功，峰值 RSS 约 3.20GB；尾部约 36 秒未落盘，完整 closure 未完成。该结果是预算截断，最终 postflight/handoff 仍由审核绑定。300 秒不是产品性能门槛，不为取得 completed 自动增加预算或重跑。

现在推进的理由是：候选语义已有验证，已保存的完整链前部可续租；继续同类小规模合成计算不能证明现场大堆或 SQLite 行为。下一诊断将检验新候选在实际失败输入上的重复 digest/payload/释放期间能否持续续租并完成该 Submit；不预先认定根因、不以成功代替正式基准或阶段退出。

## 2. 冻结产品与镜像身份

在独立 clean、已提交 worktree 检出精确产品提交，保留 legacy 链接；不合入 main 的新产品、Dockerfile、依赖或其他开发线变更。JCS/shared_kernel 改动会进入相关镜像输入，**backend、worker、Repository Service 均按该候选构建并绑定**，不将旧 e798 backend/worker 或 4497 RS 镜像称为当前候选通过或 carried。

沿该冻结提交适用的 DC67 开发节点整镜像预构建流程：CT201 只取得缓存、构建/归档，不运行测试；优先使用已有获准缓存及预置基础镜像，不升级依赖。原先要求 build network=none；已证实缓存缺失后的精确补充见 §7，不将该要求扩展为 CT201 不能取得构建制品。实际构建输入、必要非 Git context、源 tree/build-input 标签、tag、config digest、全部 RootFS DiffID、归档 SHA 与起止时间记录在 handoff。测试节点不访问公网。

经获准 LAN 传到 CT05，复核 config digest 与全部 DiffID；不能跨节点比较 inspect ID，也不能仅凭 tag 或 Git HEAD 证明镜像实际输入。候选须给出可审阅的固定构建/传输/验证命令，避免混入旧 tag。缓存缺失先补齐明确制品，不修改锁或借旧服务镜像绕过。

## 3. 最小容器验证

范围通过后，既有产品工具任务负责三个镜像构建/运输与这一项验证；原测量实施者不得同时在 05 开诊断栈。先核 SSH、节点实际占用和离线环境，在 CT05 精确候选 clean worktree 运行现有测试：

`vnext/backend/tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`

使用该提交现有 `uv-consume.sh`、`-n 0`、prebuilt 模式及预先绑定镜像。这是现有小 fixture 的三进程 upload/prepare/Submit/读取旅程，不是重跑真实数据 t3 或 W4。复用现有 harness，不修改产品或测试来放行。它覆盖新 shared_kernel 装入实际容器与 backend/worker/RS 组合路径；不再另跑重复的启动 smoke、全 Compose 文件或六包全量 runner。

先静态确认当前 harness 能使用准确三镜像及 RS context 标签，避免运行中因身份不符意外重建；不能表达时先报告具体最小工具差异，不能跳过检查。记录 hostname、UTC、起止 HEAD、clean、实际运行镜像身份、测试 exit、日志 SHA。现有用例只清理自己的临时项目/卷，绝不指向保留的 W4/诊断 source 或 target 项目。

该项结果只绑定本候选的限定容器路径，不称完整 authority runner、阶段退出或发布门禁通过。失败先保留证据并停止此链，按实际类别局部处理；不顺带跑后续诊断。通过后由独立 reviewer 核容器证据，才可进入真实输入启动候选审核。

## 4. 真实输入与目标作用域

复用 [单步诊断设计](p6-submit-single-step-diagnostic-plan.md) 已核的 05 来源材料：`p6bw4s4h120261105b`、completed_through=v2-preview 的 pre-submit checkpoint、原三卷内容、父 repo/commit、输入、规则、TTL 与唯一 composite cache entry。不复制 CT108 新状态、不重生成输入、不扫描历史所有卷、不使用任何失败或冷 catalog 诊断的目标卷。

源运行的 `run-bound RS full identity unavailable` 缺口保持显式；来源只作为已核内容的可恢复诊断输入，不能伪造 source/target MATCH 或据此 carried 正式证据。具体 launcher 仅表达这一个固定来源 → 精确 `1f9731` 三镜像的目标关系，其余内容/parent/cache/规则校验保留；不采用通用 skip identity，不复用 READY cap approval。

目标为新的独立 Compose 项目、三卷副本、幂等键与证据目录，固定至候选 manifest。运行包括真实 control DB、Dolt/RS 和唯一一次 v2-submit POST，**不只是离线 digest**；不重跑 Preview、不预热、不继续 Submit 之后的场景。旧源和已消耗诊断的卷、日志、GO/attempt marker 保持。

## 5. 一次运行的预算与观测

沿已审真实输入诊断口径：POST 前 arm 的独立 guardian 上限 **45 分钟**；worker RSS **40 GiB**、host MemAvailable **8 GiB**、相关文件系统可用 **10 GiB** 为运行停止线，每 **5 秒**读取绑定 PID/starttime/资源；启动 host available 至少 **48 GiB**，磁盘按尚需复制/落盘量加余量逐文件系统核算，已有材料不重复扣除。不能把合成诊断 300 秒扩读为此预算，也不临场延长到成功。

py-spy 使用既有固定工具和每 15 秒/最多 1 秒的纯 Python 栈方式；新 worker 镜像与解释器须重新核实际身份，POST 前要有该进程的有效业务栈，不拿旧镜像 canary 当当前镜像证据。POST 后仅既有精确已知双 interpreter-discovery 错误可在即时身份/资源复核通过后停采，必要守护继续；未知错误、必要指标不可读、身份变化、资源/截止或产品失败仍停止。不新增 profiler、GC 产品 hook 或常驻服务。

保留已有正常/异常结果、心跳/lease 日志、资源、run/state、栈和失败时的有界现场采集。尽量保留终态附近已存在的栈和日志，记录最后有效采样时间；若缺口存在就明确，不能为“补齐尾部”事后取栈冒充失败瞬间。若现有外置工具须为新镜像接线，准备最小差异并交审，不改已运行脚本。目标是判断实际输入是否完成，以及失败是否仍集中于重复 payload/digest/释放附近；离散栈只能提供相关性，不能独立证明 GC/GIL 根因。

目标业务成功、失败、R5、资源/预算截断均结束本次。失败不自动重试；观察器先停止再让原固定收尾保存证据，独立核容器/network 静止，保留三卷。未知残留或子进程未确认退出时保留占用；只释放本次自有锁。一次 POST 事实、停止分类及清理分别记录，工具退出码不代替业务结论。

## 6. 分工与放行顺序

设计拥有本文；既有产品工具任务准备固定镜像及小容器用例方案，在范围审核后执行该准备/验证；原测量实施者继续完成当前 closure 诊断 handoff，随后只准备新的真实输入 manifest/launcher；现有接续 reviewer 分别核镜像/容器结果、精确来源目标绑定及最终单次 GO。

本文不授予真实输入 POST，也不授权合 main/baseline、推送或正式测量。镜像和小容器验证按范围审核后的明确责任分配接续，不需 Owner 重确认；最终 POST 必须获得绑定完整 manifest 的一次 GO。若产品提交、镜像、输入、规则或预算改变，重新定向核差异，不复用旧 GO。

候选固定后将实际共享路径/提交同步新开发设计；合 main 前另核其冻结点。完整基准的 V→H、旧结果沿用、源身份缺口与最终门禁仍独立办理，不能用本次诊断许可替代。

## 7. CT201 构建缓存缺失后的精确补充

首次 backend 构建在 CT201 的精确 clean `1f9731` worktree 以 `--network=none --pull=false` 失败，日志 `backend-build-offline-initial.log` SHA256 `085fca8b147108fbc1c8d9d021e3ed8c7e39751342d974e6247ebcbc68be9349` 已保留：冻结 Dockerfile 的 uv 安装下载缺网络，原 `curl | sh` 未立即返回失败，之后 `uv python install` 因 uv 不存在失败。没有运行测试或影响 05，不把该失败认作产品行为失败，也不把首层退出 0 认作 uv 安装成功。

本补充只解决已发生的开发节点制品获取问题：允许在**可联网 CT201** 按相同冻结 Dockerfile、context、实际固定基础镜像与构建参数取得必需制品并构建最终镜像，具体 build network 模式在命令和 handoff 明确记录。不得称此次联网构建为离线；不要求再为了获得 `network=none` 标签而重复构建。其依据是 Owner 已允许 CT201 网络/缓存/构建用途，测试 CT 公网隔离保持；原 none 是本方案的额外限制，非产品 Contract 或正式计时口径。

使用本机已核基础镜像、`--pull=false` 并记录构建前后实际 config/全部 DiffID；不升级 tag 所指版本，不用 named-context 映射替换实际 FROM，不引入预装 uv 的替代 runtime base，不借新开发线 dependency-base，不修改 Dockerfile/锁/source 或用 ambient index 改 canonical lock。按原固定 UV/Python/Rust 版本和锁定依赖获取制品；日志必须证明实际安装/编译步骤成功，不能仅依赖被 pipeline 掩盖的退出码。保存网络模式、来源、起止、可核的制品/最终归档摘要、完整镜像身份及原始失败日志；来源中有无法独立确认的信息就标缺口，不补造旧镜像等价。

独立 reviewer 核本补充及具体构建材料，原工具任务随后接续一次受控构建/归档。构建再次失败时先据日志定位，不盲目重复或更换基础镜像。RS 已有明确缓存接口可继续沿已审流程使用，不因本补充额外改其 Dockerfile 或引入另一套构建机制。

此次具体命令须避开首次 `curl | sh` 表面成功但未安装 uv 的缓存层：使用构建器支持的定向 stage no-cache，或仅本任务构建的 no-cache，保证相关安装步骤重新实际执行；不能假定更改 network 模式必然使该层失效。不得 prune 共享缓存、删除其他任务镜像或升级基础镜像 tag。

CT05 仍只接收获准 LAN 镜像/源码制品，使用离线预填充环境及 `up --no-build`，不下载公网依赖；镜像身份检查、小容器用例、节点占用/停止及最终 POST 专属 GO 均不放宽。本补充不改变实际部署产品输入范围、测试位置或其他会话资源边界。
