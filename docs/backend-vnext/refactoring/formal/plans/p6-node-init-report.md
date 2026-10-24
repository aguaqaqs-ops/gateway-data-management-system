# P6 新测试节点核对报告（DC36 生效前置）

- 核对提交 V0：main `d99e212733951c165775026c75691ad9185c6d3d`（`vnext/` tree 与 p5-exit `bdf04c3651` 相同，为 `28d7cbe31a`）
- 依据：DC34（`p5-arch-closure-s0-owner-decisions.md` §17）、DC36（同文件 §19；生效条件为第 6 项：工具版本与 ct108 一致，各自完整运行一次权威 runner 且 exit 0）
- 节点：`gw-dms-test`（ct108，参考/取证，仅预检与同步，未跑测试）、`gw-dms-test-04`（节点 A：门禁 + carried）、`gw-dms-test-05`（节点 B：调试）
- 核对 worktree：每台 04/05 `/home/dev/gdds-p6-node-verify`（detached @ V0，`legacy` 指向主 checkout 的 `legacy`，git status clean）
- 日志根：每台 `/home/dev/gdds-p6-logs/node-init/`（0700；日志与 manifest 文件 0600；manifest 子目录 0700）
- 执行日期：2026-10-24（Asia/Shanghai）；执行人：实现者（owner 指令「P6 新测试节点核对」）

## 1. 结论

**04、05 均满足 DC36 §19 第 6 项生效条件的核心要求**：

- 工具版本与 ct108 一致（OS、Docker 29.9.1/Compose v5.6.0、containerd snapshotter、Dolt 2.1.11、uv 0.11.28、Python 3.13.5、git 2.47.3、rustc/cargo 1.97.0、rustup 组件逐项一致；见 §2）。
- 两台各自在 V0 的 clean 核对 worktree、固定环境、`GATEWAY_TEST_WORKERS=48`、umask 022 下完整运行权威 runner 一次，**exit 0**（04：2343 s；05：2331 s；逐包计数与 ct108 参考逐项一致）。
- 节点 A 的 V 门禁完整（fresh RS 镜像、runner、postflight、五包 manifest 提取、carried 演练五包全部「可沿用」）；节点 B 的 focused pytest 与 Rust 编译能力可用。

**但存在以下需 owner/reviewer 判定后才可宣布生效的事项**（见 §7）：`cargo test --workspace --locked` 在指令规定的固定环境下于 05 失败 1 例（定性为调用环境口径问题，非节点缺陷，节点能力经诊断确认完好）；TMPDIR 存在本次 runner 产生的残留未清理（按指令保留现场）；三台内核补丁版本不同（宿主属性）；真实数据目录随克隆存在于两台新节点，保留与否需 owner 决定。

## 2. 三台节点版本与身份对照

三台工具版本逐项一致：Debian GNU/Linux 13 (trixie)、Docker CLI/Server 29.9.1、Docker Compose v5.6.0、`docker context show`=default、Dolt 2.1.11、uv 0.11.28、Python 3.13.5、git 2.47.3、rustc 1.97.0 / cargo 1.97.0（`vnext/rust` 内按 toolchain 选择）、rustup 组件 cargo/clippy/rust-std/rustc/rustfmt（x86_64-unknown-linux-gnu）。核对 worktree 内复测（02 日志）与主 checkout 预检（00 日志）一致。

| 项 | gw-dms-test (ct108) | gw-dms-test-04 | gw-dms-test-05 |
| --- | --- | --- | --- |
| 角色 | 参考/取证 | 节点 A：门禁 + carried | 节点 B：调试 |
| vCPU / 内存 / rootfs | 128 / 96 GiB / 295 G 可用 | 64 / 64 GiB / 295 G 可用 | 64 / 64 GiB / 295 G 可用 |
| 内核（PVE 宿主，非节点内可换） | 7.0.14-22-pve | 7.0.14-23-pve | 7.0.14-23-pve |
| CPU 型号 | AMD EPYC 9654 | 同 | 同 |
| machine-id（前 8） | `ecabc57b…` | `b9845bde…` | `c547ec85…` |
| SSH host key ed25519 sha256（前 8） | `ba99977f…` | `2b03c6e9…` | `994577d2…` |
| Docker engine ID（克隆带入初值） | `f4933ba1-00e8-4655-9011-44c9c2d2b161` | `f4933ba1-…`（与 ct108 相同） | `f4933ba1-…`（与 ct108 相同） |
| Docker engine ID（修正后） | `f4933ba1-…`（不动） | `2a7fb80f-f28b-4cd8-a43d-bc00d8e71069` | `800564dc-81e6-462e-bc60-c7efb15743d6` |

engine ID 修正（仅 04、05，ct108 未动）：确认 `docker ps -a` 为空 → `systemctl stop docker.socket docker` → `mv /var/lib/docker/engine-id /root/docker-engine-id.cloned-from-ct108`（备份保留，0600）→ `systemctl start docker` → 新 ID 由引擎自动生成，三台互不相同；修正前后 `docker images` 列表逐项一致（`IMAGES_IDENTICAL=yes`），`gateway-repository-client-e2e:local`、`gateway-repository-client-e2e-base:local` 均未动；Storage Driver 仍为 overlayfs（`driver-type: io.containerd.snapshotter.v1`），containerd `b7a25261e029…`。

预检与 postflight 时三台/两台均无容器、无 Compose 项目、无 Dolt 进程、无 8000 监听；仓库与 worktree clean。三台镜像列表一致（6 个）：`gateway-p2r1-repository:lock-6dc9659f0aee`、`gateway-repository-client-e2e-base:local`、`gateway-repository-client-e2e:local`、`gateway-repository-service:local`、`python:3.14.6-slim-bookworm`、`rust:1.97.0-bookworm`。

## 3. 同步记录（git bundle + scp + fetch，不经 GitHub，未推送）

- 开发主机 `git bundle create main-d99e212733.bundle main`；`git bundle verify` okay（完整历史、sha1）。
- bundle SHA256 `5aa82b2e7d42ffe0fde291a5f7aec788a008b31c56058754e66f8732c95cdc7f`；scp 到每台 `/home/dev/gdds-bundles/`（0700，bundle 0600），三台节点上 SHA256 逐一核对一致后再 fetch。
- 每台：主 checkout clean 且位于 main → `git fetch <bundle> main` → `git merge --ff-only FETCH_HEAD`，rc=0。未触碰 `refs/codex/...`、`refs/archive/...`。
- 同步前三台 HEAD：`a037513879585ba7fc3c6b93bdff90f93f2ea8db`（V0 祖先）；同步后三台 HEAD 均为 `d99e212733951c165775026c75691ad9185c6d3d`，clean。

## 4. 节点 A（04）V 门禁

环境（runner、镜像构建、carried 全部一致）：umask 022；HOME=/root；LC_ALL=C.UTF-8；PATH=/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin；TMPDIR=/home/dev/gdds-test-tmp；GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1；未设置 UV_CACHE_DIR、GATEWAY_TEST_PACKAGES、HYPOTHESIS_STORAGE_DIRECTORY（carried 逐包除外）、GATEWAY_TEST_BASETEMP。

**fresh repository-service 镜像**（`./vnext/scripts/build-repository-service-image.sh`，基于 retained dependency-base `gateway-p2r1-repository:lock-6dc9659f0aee`，rc=0）：

- 构建前 `gateway-repository-service:local`（克隆带入，ct108 旧代际）：image ID `ed8c0d7bbf9e…`，candidate 标签 `6badf722c9…`。
- 构建后：image ID `627474c2f57e…`；标签 `org.opencontainers.image.revision`=`d99e212733951c165775026c75691ad9185c6d3d`（=V0，即 identity helper 的 candidate_sha）、`gateway.p2r1.build-input-revision`=`b93748c04e63be4eeece66cb5abaadf13fd7b6d3`、`gateway.p2r1.source-tree-sha256`=`sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c`、`gateway.p2r1.uv-lock-sha256`=`6dc9659f0aee…b11`（=工作树 `repository_service/uv.lock` SHA256）。四项与 identity helper / lock SHA 全部匹配。

**全量 runner**（`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`）：**exit 0**；2026-10-24T14:25:13+08:00 → 15:04:16+08:00，总耗时 **2343 s ≈ 39.1 min**。逐包/逐批：

| 包 / 批次 | 耗时 | 结果 |
| --- | --- | --- |
| shared_kernel | 1.06 s | 242 passed |
| repository_contracts | 0.28 s | 152 passed |
| repository_client | 2.82 s | 154 passed |
| backend (parallel) | 49 s | 2917 passed, 48 warnings |
| backend (serial) | 1591 s | 39 passed（2917 deselected） |
| repository_service (parallel) | 51 s | 1730 passed, 1 skipped |
| repository_service (serial) | 593 s | 205 passed（1731 deselected） |

合计 5439 passed、1 skipped（repository_service parallel 内既有跳过）、0 failed；五包 `status=passed`。

**postflight**：worktree clean @ V0；无 Dolt、容器、Compose 项目、8000 监听；五个 Hypothesis 包目录均不存在；RS 镜像四项标签与 identity helper/lock 仍匹配。

**runner 起始逐包 manifest**（从 runner 日志提取；提取时核对 HEAD=V0、clean、runner 日志 exit 0；存于 `/home/dev/gdds-p6-logs/node-init/v-manifests-04/`，0600）：

| 包 | total digest |
| --- | --- |
| shared_kernel | `550489d41489c88aeaab49e1628604e75bcee24aa7022ca9c90457bc0d3d2646` |
| repository_contracts | `d96390625db57b4e11ca8c55aa15df621fa42cc64bb427fa129b331e88f05363` |
| repository_client | `b370558e76ad11d2cde5bd9c86ca61a2981f44741548c2612917a6dbf7d30f8f` |
| backend | `f8a2e3f6ababc233a45708d6aa8c17d93027d76bac602e7bb2b2cd5d0a390ed8` |
| repository_service | `5e7b0626e25fe239a7a02035fd836f31f3b2a819b6004151bceda328ba8084cf` |

**carried 演练**（同 worktree、同 HEAD、同环境；逐包 `HYPOTHESIS_STORAGE_DIRECTORY=/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<包>`，目录均确认不存在；`test_input_closure.py manifest` + `compare`）：**五包全部「可沿用」，`changed_components=[]`，source/current total digest 逐包相等**（与上表一致）；RS 当前 identity 与镜像标签四项匹配。产物在 `/home/dev/gdds-p6-logs/node-init/v-carried-04/`（0700/0600）。carried 演练后五个假设包目录仍不存在（manifest 不创建目录）。

## 5. 节点 B（05）runner 与调试能力

**全量 runner**：与 04 同一时间窗启动；**exit 0**；14:25:13 → 15:04:04，总耗时 **2331 s ≈ 38.9 min**。逐包/批次：shared_kernel 242 passed（1.06 s）、repository_contracts 152 passed（0.28 s）、repository_client 154 passed（2.84 s）、backend parallel 2917 passed（49 s）、backend serial 39 passed（1589 s）、RS parallel 1730 passed 1 skipped（51 s）、RS serial 205 passed（593 s）。fresh RS 镜像构建 rc=0（image ID `8c783419dc1f…`，四项标签与 helper/lock 匹配；image ID 与 04 不同属构建时间戳差异，身份按标签判定）。preflight/postflight 与 04 同样全绿。carried 演练按分工未在 05 执行。

**调试能力**（05 核对 worktree，同一固定环境）：

| 步骤 | 结果 |
| --- | --- |
| backend `uv-consume.sh -C . run pytest -m unit` | rc=0，2768 passed、188 deselected，164 s |
| repository_service `pytest -m unit` | rc=0，1540 passed、1 skipped，45 s |
| `cargo build --workspace --locked`（CARGO_TARGET_DIR=/home/dev/gdds-p6-cargo-target，0700，worktree 外） | rc=0，15 s；**无需联网拉取 crate**（`~/.cargo/registry` 前后大小不变 170652 KB、cache 20276 KB，日志无 Downloaded/Updating） |
| `cargo test --workspace --locked`（同上） | **rc=101**：`gateway-compute-python --test adapter_errors::native_maps_boundary_version_unsupported` 失败，`ModuleNotFoundError: No module named 'pyarrow.lib'`；其余全部通过 |
| worktree 仍 clean @ V0 | 是 |
| `/home/dev/gdds-test-tmp` 无 runner 残留 | **否**（见 §7 第 3 条） |

**定性诊断**（`05-debug-diag-gw-dms-test-05.log`，明确标注为诊断而非正式核对）：

1. 仅设 `VIRTUAL_ENV=/home/dev/gdds-p6-node-verify/vnext/backend/.venv`：build rc=0（5 s），test rc=127——`libpython3.14.so.1.0` 不在加载路径。
2. 再加 `LD_LIBRARY_PATH=/root/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/lib`：**cargo test --workspace --locked rc=0（6 s，全部 test result ok）**。

机理：`gateway-compute-python` 的集成测试 harness 会把 `vnext/backend/.venv/lib/python3.14/site-packages` 注入解释器；固定环境未激活 venv 时 PyO3 嵌入的是系统 Python 3.13.5（无 pyarrow），cp314 的 `pyarrow.lib` 不可导入。**这是指令规定的 cargo 调用环境口径问题，不是新节点与 ct108 的差异或硬件/镜像缺陷**：两台新节点工具链、venv、crate 缓存与 ct108 一致，具备完整 Rust 调试能力。未在核对中修改任何代码或产品脚本；正式的 Rust 调试命令行口径留 owner/reviewer 决定（见 §7 第 2 条）。

## 6. 与 ct108 的耗时对比

| 节点 | runner 总耗时 | 起止 | backend par/ser | RS par/ser |
| --- | --- | --- | --- | --- |
| ct108（p5-exit 复审参考） | 批次合计 2279 s（总耗时未记录） | 未记录（日志无时间戳行；worker 数未记录） | 47 s / 1585 s | 51 s / 596 s |
| gw-dms-test-04 | **2343 s ≈ 39.1 min** | 14:25:13 → 15:04:16（+08:00） | 49 s / 1591 s | 51 s / 593 s |
| gw-dms-test-05 | **2331 s ≈ 38.9 min** | 14:25:13 → 15:04:04（+08:00） | 49 s / 1589 s | 51 s / 593 s |

ct108 参考值来源（只读查看）：`/home/dev/gdds-p5-closure-s1-gate-logs/p5-exit-fix/full-runner-6badf722c9-20261024.log`（start/end HEAD `6badf722c9e8e243e7802bb37ae1afe8893d4872`，runner exit code 0；该日志记录 start/end HEAD 与批次 elapsed_seconds，未记录墙钟起止时间）。64 核的 04/05（48 workers）与 ct108 参考在四个批次上逐批 ±6 s 内一致，瓶颈为串行批次，符合 DC36 「瓶颈不在核数」的判断。

## 7. 偏差与未决

1. **内核补丁差异（宿主属性）**：ct108 运行于 PVE 内核 `7.0.14-22-pve`，04/05 为 `7.0.14-23-pve`（不同 PVE 宿主或宿主已升级）。LXC 容器内不可更换内核；不属于 DC36 工具清单，两台新节点彼此一致。请 reviewer 确认接受。
2. **`cargo test --workspace --locked` 在固定环境下失败 1 例（05）**：根因与定性见 §5——固定环境未激活 backend uv venv 导致 PyO3 嵌入系统 3.13 解释器、pyarrow（cp314）不可导入；激活 venv 并加 uv Python 的 `LD_LIBRARY_PATH` 后同一命令 exit 0。节点能力完好，但 DC36/调试口径若要求直接 `cargo test`，需 owner 决定：修订文档化调用口径（如经 `uv-consume.sh`/激活 venv + LD_LIBRARY_PATH），或调整测试 harness。本次未修改任何代码。
3. **TMPDIR 存在本次 runner 产生的残留**：04 计 44 项、05 计 69 项（时间戳均在今日 14:24–15:04 窗口）：`tmp.*`、`uv-*.lock`、`repository-import-*.sqlite3-shm/-wal`、`pytest-of-root/`、`gateway-compose-gate-provenance.json`。五个 Hypothesis 包目录不存在（postflight 通过），但「TMPDIR 中没有 runner 残留」一项按字面不满足。ct108 今日预检时 TMPDIR 仅有空的 `gateway-runner-hypothesis`。按指令保留现场未清理，请 reviewer 复核后决定清理方式。
4. **真实数据目录随克隆存在**：`/home/dev/gateway-real-dumps` 在三台都存在（stat 仅目录本身：755 root:root；未读取、未列出内容）。DC36 第 5 项约定真实数据由 owner 放置在需要的节点；04/05 上保留还是清退（以及目录权限是否收紧）需 owner 决定。
5. **ct108 参考日志未记录墙钟起止与 worker 数**（§6）：只能给出批次耗时合计。
6. **小项**：`/home/dev/gdds-p6-logs` 父目录为 755（其内 `node-init` 为 0700，满足要求）；三台 runner 日志中 `HYPOTHESIS STORAGE` 等行正常，无警告级异常。旧 `gateway-repository-service:local` 的 candidate 标签 `6badf722c9…` 为 ct108 p5-exit 复审代际；两台按 V0 重建属预期行为（约束允许）。

## 8. 日志清单（保留在节点，待 reviewer 复核后再清理）

gw-dms-test（ct108，`/home/dev/gdds-p6-logs/` 755）：

| 文件（`node-init/` 700） | mode |
| --- | --- |
| `00-preflight-gw-dms-test.log` | 600 |
| `sync-main-gw-dms-test.log` | 600 |

gw-dms-test-04（`/home/dev/gdds-p6-logs/` 755；另有 `/root/docker-engine-id.cloned-from-ct108` 600）：

| 文件（`node-init/` 700） | mode |
| --- | --- |
| `00-preflight-gw-dms-test-04.log`、`01-engine-id-gw-dms-test-04.log`、`sync-main-gw-dms-test-04.log`、`02-worktree-versions-gw-dms-test-04.log`、`03-gate-preflight-gw-dms-test-04.log`、`03-rs-image-gw-dms-test-04.log`、`03-runner-gw-dms-test-04.log`、`03-gate-postflight-gw-dms-test-04.log`、`03-manifest-extract-gw-dms-test-04.log`、`04-carried-gw-dms-test-04.log` | 600 |
| `v-manifests-04/`（700，五包 `*.json`） | 600 |
| `v-carried-04/`（700，五包 `*.json` + `*.compare.json`） | 600 |

gw-dms-test-05（`/home/dev/gdds-p6-logs/` 755；另有 `/root/docker-engine-id.cloned-from-ct108` 600、`/home/dev/gdds-p6-cargo-target` 700）：

| 文件（`node-init/` 700） | mode |
| --- | --- |
| `00-preflight-gw-dms-test-05.log`、`01-engine-id-gw-dms-test-05.log`、`sync-main-gw-dms-test-05.log`、`02-worktree-versions-gw-dms-test-05.log`、`03-gate-preflight-gw-dms-test-05.log`、`03-rs-image-gw-dms-test-05.log`、`03-runner-gw-dms-test-05.log`、`03-gate-postflight-gw-dms-test-05.log`、`05-debug-gw-dms-test-05.log`、`05-debug-diag-gw-dms-test-05.log`（诊断，非正式核对步） | 600 |

报告 worktree（开发主机）：`/home/dev/gdds-p6-node-init`，分支 `p6-node-init` @ V0 + 本报告提交；未合并 main、未推送。
