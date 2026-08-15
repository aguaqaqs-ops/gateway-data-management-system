# P2-R6-S5 Staged Execution Guide

状态：Temporary execution coordinator - implementation pending

日期：2026-08-15

适用：`P2-R6-S5 - Build-context and image provenance`

本文件把P2-R6正式计划中的S5拆成三个严格串行、独立提交和独立handoff的实现批次，并规定
fresh independent review与exact-candidate container gate。它不拥有release identity、Docker
artifact内容、P2-R1 measurement schema、部署拓扑或S5 exit语义；冲突时必须回到正式owner，
不得用本文扩大build、launcher或Phase 2支持面。

## 1. Authority与必读顺序

每个批次开始前至少读取本文全局规则、当前批次和上一批完整handoff，并按以下顺序处理
authority：

1. 仓库根目录`AGENTS.md`；
2. [P2-R6 Operational Closure Staged Execution Plan §§2.4、4.8、5、S5、§§7–10](../../formal/plans/p2-r6-operational-closure-execution-plan.md)；
3. [P2 Versioned Repository Execution Checklist §§1–2、8–10](../../formal/plans/p2-versioned-repository-execution-checklist.md)；
4. [P2 Versioned Repository Implementation Design §§18–21](../../formal/plans/p2-versioned-repository-implementation-design.md)；
5. [Testing Conventions](../../../testing-conventions.md)与
   [Proportional Assurance Policy](../../formal/policies/proportional-assurance-and-risk-based-verification-policy.md)；
6. [P2-R1 persistent dependency cache and target launcher runbook](../../../../../vnext/deploy/p2r1-cache/README.md)；
7. [P2-R6-S4 Step E container gate provenance](../p2-r6-s4-step-e-container-gate.md)。

正式计划冻结S5目标、non-goals和exit。本文只拥有批次顺序、已确认的three-field映射、manifest
范围、focused gate、review重点和handoff格式。普通private函数名、JSON内部字段顺序和fixture
布局由实现者按现有代码风格保守选择，但不得改变第4节冻结的身份语义。

## 2. Entry snapshot与计划文档提交

本文编写前的已确认入口：

```yaml
branch: phase1/gate-ownership-repair
planning_base_sha: c421700b42f3f57895334f153fe92b48c2064ca8
s4_validated_code_sha: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
s4_provenance_documentation_sha: c421700b42f3f57895334f153fe92b48c2064ca8
s4_image_id: sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
s4_source_tree_sha256: sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6
s4_container_gate: passed
s4_exit: pass
s5_entry_ready: yes
phase_2_complete: no
production_retest_required: yes
```

本文和Phase 2临时索引先形成独立docs-only clean commit。S5-A执行者记录实际`start_sha`，确认
`planning_base_sha`与`s4_validated_code_sha`均为ancestor，并用当前helper确认计划提交未改变
Repository Service effective source digest或build-input revision。计划提交SHA只写入外部handoff，
不在本文中递归回填自身SHA。

S4 image只证明`b805d0d`的旧协议。第一处S5 build/provenance变化后它立即成为ancestor evidence；
不得表述为当前HEAD已通过S5 container gate。

## 3. S5需求与设计基线

### 3.1 Stage outcome

S5必须同时完成：

- builder、Compose build harness和target launcher从同一versioned manifest/helper计算身份；
- clean exact candidate、build-input revision和effective source digest是三个独立字段；
- image labels、local checkout、remote detached checkout和launcher manifest对三个字段逐一相等；
- docs-only、source、lock、Dockerfile/build-definition和dirty-tree变化获得确定、可测试的分类；
- stale、missing、malformed或互相矛盾的label/digest/image identity全部fail closed；
- remote build、`docker save | load`和local inspection保持同一immutable image ID；
- 旧`git archive HEAD` whole-repository digest、v2 manifest和复用`build_revision`表达两种身份的
  路径被删除，不保留fallback；
- exact-candidate Step E完成后才声明S5 exit。

### 3.2 Confirmed decisions

以下决定已在2026-08-15 S5 readiness访谈中由用户确认：

1. `org.opencontainers.image.revision`唯一表示literal clean `candidate_sha`；
2. 新的`gateway.p2r1.build-input-revision`唯一表示`build_input_revision`；
3. `gateway.p2r1.source-tree-sha256`唯一表示`source_tree_sha256`；
4. `gateway.p2r1.uv-lock-sha256`保留为辅助dependency identity，不替代三个主字段；
5. effective source继续覆盖`vnext/repository_service/**`和
   `vnext/repository_contracts/**`的完整tracked source closure，包括其中README和测试；
6. build-definition scope显式加入`.dockerignore`、正式build script及manifest/helper；
7. formal build与launcher拒绝整个worktree的tracked/untracked dirty状态；
8. provenance manifest一次性升级，所有current consumer同批迁移，拒绝旧schema且不保留fallback；
9. S5只拥有build/transfer/launcher identity smoke；W1/W2、完整cgroup/v8和lifecycle exit仍归
   S6/S7/S10。

### 3.3 Users, flow and non-functional baseline

S5的直接使用者是release operator、retained-cache builder、gate-host launcher和调用共享helper的
Repository build harness；不是Repository Service API caller。唯一formal流程是：

```text
clean exact checkout
  -> canonical helper computes candidate/build-input/source identity
  -> builder emits the three labels
  -> immutable image transfer preserves image ID
  -> launcher recomputes from the same checkout and compares every field
  -> verified runtime manifest is mounted read-only
  -> identity smoke or later S10 measurement may start
```

非功能要求是deterministic、offline-capable、linear in effective file count、host-path independent和
fail closed。S5不设置新的性能数字，但helper不得读取`vnext/rust/**`、构建Docker context或启动
provider来计算identity。受控同机builder/launcher仍属于当前trusted deployment domain；S5不新增
secret、network service、daemon、socket、UID、capability或持久evidence store。

部署假设保持现状：remote builder有normal Git detached checkout、Python 3、Docker和retained
dependency cache；gate host通过可审计`docker save | load`取得同一image。S4只证明该路径曾可用，
Step E仍需重新检查当前availability。主要风险是manifest漏项造成false match、字段复用造成false
provenance、dirty/untracked输入绕过candidate和新旧schema双authority；第4、10、11节分别用
single manifest、hard cutover、negative matrix和exact candidate gate关闭。

兼容性采用一次性内部迁移，不支持v2/v3并存。延后事项只有W1/W2、完整Compose lifecycle、final
candidate seal、canonical v8和Phase 2 exit；这些不改变S5协议，也不由S5证据提前关闭。

### 3.4 Explicit non-goals

所有批次共同禁止：

- whole-repository content digest、`git archive HEAD`或把`vnext/rust/**`加入sync/hash；
- candidate commit自引用自己的SHA，或provenance文档回填自身commit SHA；
- 允许formal dirty build的override、advisory warning或“best effort”identity；
- 在label mismatch时自动重建、自动选择另一checkout或接受短SHA；
- 第二套manifest/helper、shell内重复实现hash算法或consumer-local path list；
- 改变production Service业务行为、public API、repository disk format或snapshot protocol；
- 改写P2-R1 canonical measurement参数、record数量、cgroup topology或capacity结论；
- 开始S6 W1/W2、S7 Compose lifecycle、S9 seal、S10 final production gate或S11 handoff；
- 修改dependency版本、base image、Dolt/uv版本或production package closure，除非S5实现本身证明
  当前identity协议无法在既有closure内完成并触发第14节reopen；
- 在一个批次中顺带开始下一批或P2-R6-S6。

## 4. Frozen three-field protocol

### 4.1 `candidate_sha`

- 值是formal build所用checkout的literal、lowercase、40-character Git commit SHA；
- 必须等于整个clean worktree的`HEAD`，local与remote detached worktree一致；
- image label为`org.opencontainers.image.revision`；
- candidate只在所有S5 production/test/build/deploy变化提交后封板，不写入candidate自身；
- docs-only provenance commit发生在gate之后，只记录candidate，不成为已验证image revision。

P2-R1 matrix中已经发布的内部`build_revision`结果名不在S5改写measurement schema。其值在新协议
下只能映射`candidate_sha`，不得继续表示`build_input_revision`。新manifest、launcher和image
inspection必须使用显式`candidate_sha`字段，不能从旧字段名反推另一种身份。

### 4.2 `build_input_revision`

值是当前candidate ancestry中最近一次触碰versioned manifest所列build input的literal
40-character commit SHA。至少覆盖：

- effective source roots：`vnext/repository_service/**`、
  `vnext/repository_contracts/**`；
- `vnext/.dockerignore`；
- `vnext/scripts/build-repository-service-image.sh`；
- `vnext/deploy/compose.yaml`中的Repository image build definition；
- canonical manifest/helper本身；
- Dockerfile已由`vnext/repository_service/**`覆盖，不建立重复path owner。

计算必须使用结构化argv调用Git，不拼shell command。missing history、non-resolving SHA、非40位值、
manifest path缺失或manifest未被自己覆盖均为错误。docs-only path不在manifest时，candidate变化但
`build_input_revision`和`source_tree_sha256`保持不变；这不允许把docs commit当成已构建candidate。

image label固定为`gateway.p2r1.build-input-revision`。不得继续让
`org.opencontainers.image.revision`承载该值。

### 4.3 `source_tree_sha256`

effective source范围保持当前较强边界：两个Repository Python package完整tracked closure，而不是
仅Dockerfile `COPY`子集。README、tests、Dockerfile、lock和package metadata都在对应root内，变化
必须改变digest。只排除manifest明确列出的generated/non-source artifact，例如`.venv`、Python
bytecode和pytest/mypy/ruff cache；普通untracked文件不通过formal clean preflight，不能靠ignore
掩盖dirty candidate。

唯一helper使用稳定、版本化编码：

1. 读取versioned manifest并验证schema与path containment；
2. 对每个root取得排序后的repository-relative POSIX path；
3. 只接受manifest policy允许的tracked regular files；symlink、特殊文件、越界或重复path fail
   closed，除非当前tracked source事实要求并先修订本文；
4. digest输入至少区分manifest/version、relative path和exact bytes，字段间使用不歧义的length或
   NUL framing；
5. 输出严格为`sha256:`加64位lowercase hex；
6. local、remote、builder、harness和launcher都调用该helper，不复制算法。

image label固定为`gateway.p2r1.source-tree-sha256`。

### 4.4 Supporting dependency identity

`gateway.p2r1.uv-lock-sha256`继续保存Repository Service lock的64位lowercase SHA-256，并与
Dockerfile默认值、dependency-base label和checkout lock file相等。它是独立辅助检查，不得被
用作`source_tree_sha256`或`build_input_revision`的替代。

S5不改变Dolt、uv、connector或PyArrow版本，但launcher继续验证既有精确版本label。

### 4.5 Manifest schema and consumer migration

canonical manifest至少表达：schema/version、effective source roots、generated artifact exclusion、
build-definition paths和digest encoding version。路径必须repository-relative、去重、排序并受root
containment约束；不接受absolute path、glob逃逸或host-dependent配置。

provenance runtime manifest升级到新版本，至少明确记录：

```json
{
  "candidate_sha": "<40 hex>",
  "build_input_revision": "<40 hex>",
  "source_tree_sha256": "sha256:<64 hex>",
  "image_digest": "sha256:<64 hex>"
}
```

另保留lock、tool versions、cache condition和project identity等当前必需字段。旧
`p2-r1-provenance-v2`、missing field或把candidate/build-input写成同名`build_revision`的manifest
必须被拒绝，不做兼容推断。若两个SHA因同一commit恰好相等，仍必须作为两个字段独立计算、记录
和比较。

### 4.6 Clean and formal-mode boundary

retained-cache build script与formal target launcher均要求整个repository worktree无tracked、
untracked或unmerged变化。检查失败发生在digest、Docker build、container或evidence output之前。
不提供formal bypass环境变量。

开发者可直接使用非正式Docker命令做诊断，但该image缺少或不匹配三个formal labels时必须被
Compose harness/launcher拒绝，不能形成`image_matches_build_context=true`或S5 evidence。

## 5. Cross-batch invariants

1. S5-A、B、C严格串行。每批从上一批clean green commit开始，提交并输出完整handoff后停止。
2. A先建立唯一manifest/helper和field model；B只消费A冻结的协议改builder/image producer；C再
   改launcher/runtime manifest和跨host verifier。后续批次不得各自发明path list或hash实现。
3. 中间批次允许旧consumer尚未全部迁移，但不得出现两个都可产生formal PASS的authority；旧路径
   必须显式标为stale/non-formal，并在C exit前删除。
4. 三个主字段逐一计算、逐一写label、逐一比较。相等的SHA值不允许合并字段。
5. helper和consumer遇到missing、malformed、dirty、unresolvable、path escape或identity mismatch均
   fail closed，不自动retry/rebuild或降级whole-archive。
6. build script不接受caller提供但未经本地helper重算核对的identity override；Compose harness也
   不得通过环境变量注入任意label后宣称匹配。
7. target launcher在任何systemd unit、container、run directory或measurement output创建前完成
   clean checkout、image labels和三个field核对。
8. remote/local image identity以immutable image ID为准；tag相等不构成transfer proof。
9. S5不改measurement workload、business runtime、data volume或cgroup topology。directed smoke只
   证明identity链，不提前消费S10 formal result。
10. 删除/改名任何旧field、env、helper或shell hash前保存exact consumer `rg`；C做全仓consumer
    closure。
11. 测试按身份行为命名；同构missing/malformed/stale case使用模块级共享参数表，不复制测试。
12. 纯manifest/parser/Git argv/harness测试为unit，不创建Dolt HOME、不启动Docker。真实image build、
    transfer或container inspection只在Step E执行，不新增宽泛marker。
13. A/B/C中间提交不重建formal image。每份handoff标记current image gate `stale/deferred`，last
    verified image仍绑定S4 `b805d0d`。finding关闭后的S5 exact candidate只正式重建一次。
14. candidate封板后不得amend/rebase/squash；Step E失败若需改tracked build input，形成新candidate
    并全量重跑S5 Step E。

## 6. Delivery sequence与conversation protocol

```text
docs-only execution baseline
  -> S5-A canonical manifest, helper and identity model
  -> S5-B builder, Docker labels and Compose build harness
  -> S5-C target launcher, runtime manifest and source closure
  -> fresh independent S5 review and finding closure
  -> exact-candidate Step E and provenance
  -> P2-R6-S6 handoff (only after external W1 descriptor is ready)
```

| Batch | Outcome | Suggested commit |
| --- | --- | --- |
| S5-A | versioned input manifest、唯一helper、three-field model与pure unit matrix | `fix(repository): define repository image provenance inputs` |
| S5-B | clean builder、三个image labels、build harness与stale-image checks | `fix(repository): emit exact repository image provenance` |
| S5-C | launcher/runtime manifest hard cutover、consumer closure、runbook与source gate | `fix(repository): verify repository image provenance end to end` |

每批推荐使用新对话，禁止并行。新对话只接收本文、上一批完整handoff和当前批prompt。整体review
与Step E分别使用新的干净对话；review不以实现者handoff替代代码审计，Step E不夹带tracked修改。

## 7. S5-A - Canonical manifest, helper and identity model

### Objective与allowed scope

建立第4节的唯一versioned input manifest/helper以及三个field value object/structured result。允许修改
现有`build_context_digest.py`、其focused tests和必要的digest documentation。不得修改Dockerfile
labels、build script调用协议、Compose harness、target launcher或runtime manifest。

优先演进现有helper，避免在A阶段引入第二实现。若确需移动路径，必须在同一commit迁移所有立即
依赖它的unit consumer并留下后续B/C唯一入口；不能保留两个可独立计算formal digest的脚本。

### Required work

- 增加versioned、machine-readable manifest并验证self-coverage、path去重和containment；
- 实现`candidate_sha`、`build_input_revision`和`source_tree_sha256`的独立结构化计算；
- 把source roots和build-definition paths从散落常量收敛到manifest；
- whole-worktree clean检查包含tracked、untracked和unmerged状态；
- source digest使用稳定framing并拒绝symlink/special/missing/duplicate/escape；
- `build_input_revision`只以manifest path set调用`git log`并要求40位resolvable SHA；
- 保留明确CLI子命令，一次输出单值或versioned JSON，不输出host path；
- A可暂留现有`build-revision` CLI作为到B的串行过渡，但它只能委托canonical helper返回显式
  `build_input_revision`，必须标为non-formal/deprecated，不能产生three-field PASS；B迁移完builder
  后删除该alias，S5-C exit不得残留。

### Required evidence

至少覆盖：

- same manifest/tree产生确定digest；文件顺序和host checkout path不影响结果；
- source、README/test、lock、Dockerfile变化改变source digest；
- `.dockerignore`和build script变化改变build-input revision但不伪造source bytes变化；
- digest外docs-only变化只改变candidate SHA；
- tracked/untracked/unmerged dirty全部拒绝；
- missing/malformed/duplicate/absolute/escape manifest entry和unsupported schema拒绝；
- ignored generated cache不影响digest，但普通untracked文件仍被clean preflight拒绝；
- short/unresolvable/missing Git revision拒绝；
- helper CLI输出shape、安全错误和return code稳定；
- parked-Dolt `-m unit`证明pure provenance tests无provider dependency。

运行focused pytest、repository_service ruff/mypy和`git diff --check`。完成green commit和handoff后
停止，container gate标记stale/deferred。

### Prompt S5-A

```text
执行P2-R6-S5-A。完整约束见
docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s5-staged-execution-guide.md。

开始前读取§§1-7及正式provenance authority，记录start_sha，确认S4 candidate/provenance和S5
planning docs均为ancestor且worktree clean。只实现versioned effective-input manifest、唯一helper、
three-field identity model和pure unit matrix。不得修改Dockerfile/build producer、Compose harness、
target launcher或runtime manifest。通过required gates后提交、输出§13 handoff并停止。
```

## 8. S5-B - Builder, Docker labels and Compose build harness

### Objective与allowed scope

让正式build producer和Compose build harness只消费S5-A canonical helper，构建带三个独立label的
image并在重用前严格核对。允许修改Repository Service Dockerfile、正式build script、Compose的
Repository image build args、Compose build harness、相关static/unit tests和build README。不得修改
target launcher、runtime provenance manifest、P2-R1 matrix或执行formal remote gate。

### Required work

- Dockerfile接收独立`CANDIDATE_SHA`、`BUILD_INPUT_REVISION`和`SOURCE_TREE_SHA256` build args；
- 三个args格式不合法或为`unknown`时formal build fail closed；
- label按§4.1-4.3固定映射，lock/tool labels保持现有精确检查；
- build script先验证整个worktree clean，再调用helper一次取得同一versioned identity result；
- caller-supplied identity只有与helper重算逐字段相等才可继续，不能作为override authority；
- dependency-base选择继续绑定lock SHA，不把dependency-base revision冒充candidate；
- Compose harness在重用image前同时验证三个label和lock label；缺一或任一stale均触发明确失败/
  rebuild路径，formal结果不得只比较两个字段；
- Compose的Repository image build stanza显式传递三个args，不保留会把candidate/build-input合并的
  `BUILD_REVISION` build arg；runtime environment迁移留给C；
- 更新静态Dockerfile/build-script tests和README命令，移除whole-archive或旧BUILD_REVISION示例；
- 保存旧env/build arg/label consumer inventory，C继续关闭launcher/runtime部分。

### Required evidence

至少覆盖：

- build script向Docker传递三个独立、40/40/digest格式正确的args；
- candidate与build-input恰好相等时仍传三个独立args；
- docs-only/source/lock/Dockerfile/build-script classification符合manifest；
- whole dirty tree、caller override mismatch、unknown/short SHA在Docker调用前失败；
- Dockerfile包含三个label且不再用`BUILD_REVISION`表达build-input；
- harness匹配全部字段时可复用，missing/stale/malformed任一字段时拒绝；
- stale tag但不同immutable image ID不被视为相同image；
- build failure/timeout错误不输出token、proxy secret或伪造provenance pass；
- dependency-base lock mismatch保持fail closed；
- parked-Dolt unit、ruff/mypy和`git diff --check`通过。

本批不把mocked Docker argv test称为directed image smoke。完成green commit和handoff后停止，formal
container gate仍为stale/deferred。

### Prompt S5-B

```text
执行P2-R6-S5-B。开始前读取S5 guide §§1-6、§8和完整S5-A handoff；核对A commit为ancestor且
worktree clean。只迁移Dockerfile、retained-cache build script和Compose build harness，使它们消费
唯一helper并产生/验证candidate、build-input和source-tree三个独立label。不得修改target launcher、
runtime manifest或执行final remote build。通过required gates后提交、输出§13 handoff并停止。
```

## 9. S5-C - Target launcher, runtime manifest and source closure

### Objective与allowed scope

把target launcher、runtime provenance manifest和所有current identity consumer迁移到同一S5协议，
删除whole-archive/v2/overloaded revision路径，并完成source candidate准备。允许修改private target
launcher、Compose env wiring、private measurement provenance adapter、runbook和focused tests；只允许
为迁移当前consumer做最小owning-scope改动，不改变measurement workload/output acceptance。

### Required work

- launcher直接调用canonical helper取得三个字段，不在shell重写path/hash算法；
- image inspection要求三个主label、lock/tool labels和immutable image ID格式完整；
- launcher在创建run directory、systemd unit、container或output前完成whole-tree clean和逐字段比较；
- runtime manifest升级并显式保存三个字段；v2/missing/legacy-only manifest拒绝；
- Compose env将candidate与build-input分开传递；旧`GATEWAY_P2R1_BUILD_REVISION`若仍为冻结
  measurement presentation input，只能承载candidate且不得作为manifest authority；
- measurement metadata从verified manifest取得candidate/build-input/source identity，CLI参数不得
  覆盖verified值；既有`build_revision`输出若保留，只映射candidate；
- `docker save | load`后的local verifier按image ID和三个labels核对，不以tag/name代替；
- 更新runbook exact checkout/build/transfer/launcher命令，删除`git archive HEAD`示例；
- 全仓搜索并分类旧helper、`BUILD_REVISION`、whole-archive、v2 manifest和overloaded env consumer；
- 运行S5 source gates，形成independent review ready的clean commit。

### Required evidence

使用共享参数表覆盖三个主label的missing/malformed/stale/contradictory组合。另至少覆盖：

- launcher/helper在同一clean checkout计算与builder完全相同的三个值；
- docs-only、source、lock、Dockerfile、dirty-tree分类矩阵；
- launcher拒绝whole archive digest、v2 manifest和legacy-only revision；
- preflight失败前无run directory/systemd/container/output副作用；
- remote/local相同image ID和labels通过，不同ID、tag drift或任一label drift拒绝；
- verified manifest不能被CLI/env降级覆盖；
- P2-R1 matrix既有workload、record count、cgroup和cleanup tests不回归；
- current code/runbook无`git archive HEAD` provenance命令或第二套effective path list；
- parked-Dolt unit、affected tests、五包ruff/mypy和`git diff --check`通过。

source gate至少执行：

```bash
cd vnext/repository_service
uv run pytest -m unit
uv run ruff check .
uv run mypy

cd vnext/<each-other-python-package>
uv run ruff check .
uv run mypy

./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
git diff --check
```

若S5新增真实Docker测试文件，ignore inventory必须登记精确path/nodeid；纯Dockerfile、script、launcher
和harness static/unit tests不得排除。完成green commit和handoff后停止，不执行final image build。

### Prompt S5-C

```text
执行P2-R6-S5-C。开始前读取S5 guide §§1-6、§9、testing conventions和完整S5-B handoff；核对A/B
commits为ancestor且worktree clean。只关闭target launcher、runtime manifest、current consumer迁移、
runbook和source gates；删除whole-archive/v2/overloaded identity路径。不得开始W1/W2、cgroup/v8 final
gate或S6。全部source gate green后提交、输出§13 handoff，标记independent review ready并停止。
```

## 10. Fresh independent review与finding closure

S5-C结束后新开对话，对planning baseline与S5-A至C完整range做独立只读review。reviewer先核对正式
authority、manifest实际范围、所有consumer、label/manifest/env mapping、Git/clean preflight顺序、
Docker producer、launcher side-effect boundary和测试，不复述handoff代替代码审计。

至少检查：

- 三个字段没有任何别名复用或由一个字段推导另一个字段；
- manifest覆盖两个source roots、`.dockerignore`、build script和自身，没有absolute/escape/duplicate；
- source digest未缩小到Docker COPY子集，也未扩大到whole repository；
- Dockerfile/build script/harness/launcher只调用一个helper/path policy；
- `org.opencontainers.image.revision`确实是candidate，不是build-input；
- clean check覆盖whole tree且发生在build/runtime side effect之前；
- caller env/CLI不能伪造或覆盖helper/verified manifest；
- v2/whole-archive/missing/malformed/stale identity全部fail closed；
- P2-R1 frozen measurement schema若保留`build_revision`，其值只映射candidate；
- S6/S7/S10 evidence未被伪称为S5 pass，S4 image未被称为current。

finding按severity、位置、后果和复现证据报告。只修改owning scope，逐轮提交并重跑affected gates。
所有finding关闭、source gates green且worktree clean前：

```yaml
S5_exit: no
Step_E_ready: no
P2-R6-S6_ready: no
```

## 11. S5 exact-candidate Step E

finding关闭后封板exact S5 code candidate。S5直接修改Docker/build/launcher identity boundary，必须为
该candidate重建image；不得使用S4 `b805d0d`/`0c93c04`关闭S5。

### 11.1 Identity and build gate

沿用S4已证明的clean detached worktree、retained cache、Git bundle和`docker save | load`流程，
但使用S5 canonical helper。记录并核对：

- literal 40-character candidate SHA，local/remote HEAD与whole-tree clean status；
- manifest schema/digest encoding version和exact input inventory；
- local/remote helper计算的candidate、build-input revision、source digest和lock SHA；
- build command、cache status、build args和build-input revision；
- remote/local immutable image ID相等；
- remote/local三个主labels及lock/tool labels相等并精确匹配helper；
- provenance doc不进入verified effective digest。

任一short/non-resolving SHA、dirty tree、manifest/label/digest mismatch、missing field或image ID drift都是
identity gate失败。tracked修复必须形成新candidate并重建；不能只改报告或同commit重跑变绿。

### 11.2 Directed classification and launcher gate

至少执行：

1. canonical helper在clean local和remote detached checkout输出完全相同的versioned identity；
2. docs-only fixture只改变candidate；source fixture改变candidate/build-input/source；
3. lock fixture改变candidate/build-input/source/lock；Dockerfile fixture改变candidate/build-input/source；
4. `.dockerignore`或build script fixture改变candidate/build-input，source按manifest保持稳定；
5. tracked、untracked和unmerged dirty fixture均在Docker/launcher side effect前失败；
6. exact candidate在remote retained-cache builder成功构建，三个labels/lock/tool labels正确；
7. stale/missing/malformed label和v2/legacy manifest directed case全部非零且无formal output；
8. `docker save | load`后local image ID与remote一致，tag-only或different-ID case被拒绝；
9. target launcher preflight消费同一helper/manifest并接受exact image，不运行完整v8 formal matrix；
10. teardown后本轮container/network/volume/run-dir/systemd instance inventory为零。

S5 Step E只做最小identity image/launcher smoke。不得提前运行或宣称S6 W1/W2、S7 lifecycle、S10
canonical v8/full exit。任一required gate失败时S5 no-go；build-input修复产生新candidate并重跑全部
Step E。

### 11.3 Provenance

container通过后，只在verified effective digest之外提交独立记录，例如：

`docs/backend-vnext/refactoring/temporary/p2-r6-s5-step-e-container-gate.md`

外部handoff记录：

```yaml
validated_code_sha: <exact S5 code candidate>
container_validated_code_sha: <same S5 candidate>
provenance_documentation_sha: <later docs-only commit>
candidate_sha: <same S5 candidate>
build_input_revision: <exact manifest-derived commit>
source_tree_sha256: <effective digest>
image_id: <exact immutable image id>
production_retest_required: yes
phase_2_complete: no
P2-R6-S5_exit: pass
P2-R6-S6_ready: yes/no according to external W1 descriptor
```

S5技术exit与S6 entry必须分开：S5可以pass，但external W1 descriptor未ready时固定
`P2-R6-S6_ready: no`并记录external blocker；不得伪造descriptor或把其缺失写成S5失败。

## 12. Validation与container记录规则

每批报告必须包含：

```text
Current_HEAD:
Container_rebuild_required: yes
Reason: S5 changes build/provenance boundary
Last_verified_image_revision: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
Last_verified_source_tree_image_id:
  sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6 /
  sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
Container_gate_for_current_HEAD: stale/deferred/passed
Deferred_gates_nodeids: S5 exact-candidate Step E identity image/launcher smoke
Required_execution_point: findings关闭后的S5最终候选Step E
```

A/B/C不得用unit mock、Dockerfile text test或S4 image写`passed`。只有§11 exact candidate完成后当前
candidate container gate为`passed`。任何A/B/C中间commit触碰manifest/helper/Dockerfile/build
script/launcher都保持old evidence `stale`。

## 13. Batch handoff template

每个S5-A至C对话结束时完整输出：

```text
round: P2-R6-S5-<A|B|C>
start_sha:
commit_shas:
head_sha:
required_ancestors:
worktree_clean: yes/no

objective_closed:
modified_scope:
deleted_scope:
explicit_non_goals_preserved:
identity_or_manifest_changes:

manifest_schema_version:
candidate_sha_semantics:
build_input_revision_semantics:
source_tree_sha256_semantics:
consumer_inventory:

validation_commands:
  - command:
    result: pass/fail + exact counts/key output
first_failures_and_fixes:
consumer_search_before_delete:
old_reference_searches:
runtime_cleanup:

known_limitations:
validated_source_scope:

Current_HEAD:
Container_rebuild_required: yes
Reason: S5 changes build/provenance boundary
Last_verified_image_revision: b805d0d5f3c6164875319bd5e4b7b12d998cfe96
Last_verified_source_tree_image_id:
  sha256:dde82b4acfc86e6561f5c195daef31a75ae7e3417f9f808da41a7af6f37ae7f6 /
  sha256:0c93c04b15501b9db536016a729a6520252fca445dc0746a4f04c335f54de26e
Container_gate_for_current_HEAD: stale/deferred/passed
Deferred_gates_nodeids:
Required_execution_point: findings关闭后的S5最终候选Step E

batch_exit: pass/no-go
next_batch: P2-R6-S5-<next>
next_batch_ready: yes/no
next_entry:
```

不能用“主要通过”“仅环境失败”替代命令结果。未提交、worktree dirty、required source gate失败、
authority冲突、两个formal helper共存或container trigger未登记时，`next_batch_ready=no`。

新对话入口：

```text
执行P2-R6-S5-<batch>。

完整约束见：
docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s5-staged-execution-guide.md

上一批次handoff：
<paste complete handoff>

核对当前HEAD、required ancestors、worktree和上一批门禁；只执行当前batch。完成提交和handoff后
停止，不开始下一batch，不提前构建最终镜像。
```

## 14. Stop与reopen conditions

出现以下任一情况时停止当前批次，不用局部补丁扩大S5：

- accepted Docker/release平台不能提供三个独立labels或immutable image ID；
- effective source必须包含whole repository、`vnext/rust/**`或host-specific files才能判定；
- actual production build不经过当前retained-cache script且存在第二个同等authority builder；
- target launcher执行环境不能访问normal Git checkout或运行canonical helper；
- formal流程必须接受dirty tree、file-only sync、short SHA或无法解析的candidate；
- current tracked source包含必须支持的symlink/special file，需重新定义digest encoding；
- P2-R1 frozen measurement schema无法把旧`build_revision`安全映射candidate，必须改变formal
  measurement contract；
- hard cutover需要跨版本同时接受v2/v3 manifest或双env authority；
- container gate需要修改S6/S7/S9/S10拥有的capacity、lifecycle、seal或final gate scope；
- formal owner、本文和真实builder/launcher事实出现无法按authority顺序消解的冲突。

上述情况记录`batch_exit=no-go`、`next_batch_ready=no`并指出需要修订的owner。普通private函数名、
manifest文件名、JSON字段顺序、test fixture布局和错误文本不是reopen理由。
