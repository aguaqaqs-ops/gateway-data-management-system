# Phase 6 S5 A 交接

当前状态：修后候选`eb64578925398a6402f6e7b21790226c5f4e78e6`源码CODE_GO，06复验进行中，**证据尚未通过，B未启动**。设计CLEAR、源码CODE_GO与实际验证分别记载。

## 实现与独审

A实现了完整单表有向语义身份、同源native输入投影、Comparison neutral facts/artifact/STANDARD risk codec及恢复facade、当前绑定重算和Risk完整候选事件。业务golden、SQL、HTTP DTO、依赖与锁文件未变。新增内部格式和各owner Contract直接改到目标形态，不保留旧repr身份或兼容别名。B持久缓存与C应用接线尚未实现。

功能候选`5a74dfd0684f45a826e485d48d73a6ea66dd7126`及格式候选`ad043152b1604da1ff56ec67f1513e4fd9b66456`由同一独立Sol审核者连续复审为CODE_GO；发现与关闭详情、逐字原件见[A审核归档](p6-s5-a-review.md)。此结论没有代替编译和focused检查。

## 首次实际检查及修复

| 项目 | 原始事实 |
| --- | --- |
| 节点 / 入口 | `ct107-gw-dms-06` / `gw-dms-06.lan`；唯一测试者执行外置`a-focused.sh` |
| 起止HEAD | 均为`ad043152b1604da1ff56ec67f1513e4fd9b66456`，开始和收尾worktree clean |
| 节点UTC | `2026-11-09T06:15:29Z`–`2026-11-09T06:16:28Z` |
| 执行范围 | 第一项`backend-native-sync`，offline、强制重装native，Rust jobs=4；尚未进行实际计算，M24授权未扩大 |
| 结果 | maturin/Cargo编译四处E0433；command exit=1，tee exit=0，入口exit=1 |
| 后续 | build-input、五包ruff/mypy、Rust fmt/clippy/core focused及backend focused全部未运行；没有继续carried或验收 |
| 现场 | 原子占用归本人，资源核空后释放；failed uv/tmp/Cargo现场保留，未重试原候选 |

原件目录：`/home/dev/gdds-s5-logs/execution/a-focused/20261109T061526Z-ad043152b1604da1ff56ec67f1513e4fd9b66456/`。关键step log：`remote-evidence/backend-native-sync.log`，SHA256=`16905a439faa5a29a7f458dada14fd8f57739daf83a6e6ebd67382e2e3599067`；完整stdout SHA256=`15094ca2f2a622b76a7ff8fe73ee167f30b51a5918c673b83dbb15981b2dbd73`。环境使用本节点预填uv/Cargo缓存、无公网或代理；工具链1.97.0四工具均解析到`/home/dev/.cargo/bin`，uv0.11.28，TMPDIR位于磁盘`/home/dev/gdds-test-tmp`。源码通过获准LAN bundle传入，bundle SHA见协调记录。

失败属于产品源码：FFI新增直接引用未声明的`serde_json`和`gateway_shared_kernel`。修订`5351170224c6bbe4997074338292fb04b380e64f`将JSON解析/元数据构造与identifier检查移到已有core owner的实际helper，FFI只调用core facade；四个Rust文件，无依赖或锁修改。同一原审R5为CODE_GO。07格式准备曾因未进入Rust selector目录而停止，修正后同一步从头完成`cargo fmt --all`（06:36:46–06:36:47Z、exit0），旧错误日志保留；06当时他人有效占用的准入冲突也保留，未抢占资源。最终三文件纯格式补丁SHA256=`6c5d54755170626dd1d928a8339e0124fffd2237905e9fc991283fa59655dedf`，应用为`c1a5332a87`，R6逐字核补丁并CODE_GO，Rust tree=`180d191566f9eb95729994ea9ef3284e7fa54b78`。

06再次空闲且离线缓存合格后，唯一测试者按已窄审的参数化稿`a-focused-next.sh`（SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`）原子取得本人标记，传输并校验固定c1a533源码bundle（SHA256=`994f8daba45d13971c2a3f4855d8d1ad53eb1a3e86e2665ea59d03e0151f00d2`），在clean detached WT于06:39:49Z开始修后检查。Cargo target置于本次独立runroot，未删除首次失败的共享target/现场。当前仅知道native sync已启动，尚不宣称编译或后续检查PASS。

## 连续复验与修订

下列均在06本人原子占用、固定clean已提交detached WT上按同一必要检查顺序执行，起止HEAD等于该行候选。各次首非零即停，tee均为0，失败uv/Cargo/tmp与原件保留；收尾资源核空、本人标记已释放。UTC取原始session，步骤开始可稍晚于session。失败不能作qualified runner来源，未跑的后续项不能写PASS。

| 候选 | Session UTC（2026-11-09） | 首失败 / 入口exit | 实际边界与修订 |
| --- | --- | --- | --- |
| `c1a5332a87` | 06:39:48–06:41:11 | backend mypy / 1 | native/build-input及此前静态通过；新增测试20项类型错误。ee234显式字段/narrowing/变量改名，无ignore或预期改动；RS静态/Rust/focused未跑。 |
| `ee234028e0` | 06:44:47–06:46:29 | Rust clippy / 101 | 五包ruff/mypy、native/build-input及fmt通过；恢复函数8参数。0ddc按既有records builder边界增加局部说明/allow，无函数体变化；core/backend focused未跑。 |
| `0ddc7ec648` | 06:48:29–06:50:35 | backend parallel / 1 | 前述静态、clippy及core cache四测试通过；56失败/222通过。18b修helper误把所有OrderedMetadata当ORDERED声明，以及绕过owning schema的Parquet测试；产品guard/golden未改，serial未跑。 |
| `18b79112fa` | 06:59:31–07:01:37 | backend parallel / 1 | 前述必要静态/Rust/core通过；3失败/275通过。eb645修STANDARD不消费的ordered metadata误入key，并据固定旧源修KEYLESS空values、SET真实NULL→x变更向量；serial未跑。 |

修订均由同一独立Sol原审连续复审为CODE_GO，原件逐字归档，不能由这些源码结论反推实际检查已通过。KEYLESS和SET独立依据为既有golden声明的固定旧源码`4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec`及`a9da0c59277e3179f34d646eabcd9c185917ae05`，原审已核相同行为和手算frame；无业务golden重录。两份外部binding诊断稿最终未执行、未SSH准入，不作为证据。

外置原件根为`/home/dev/gdds-s5-logs/execution/a-focused/`，对应目录与关键日志SHA如下。完整steps/session、所有step日志及清单在同目录，原审核者逐项核收。

| Run目录 | 首失败日志SHA256 | steps.tsv SHA256 |
| --- | --- | --- |
| `20261109T063945Z-c1a5332a8722d3736280d8b60059944e329b8697` | `03ac3643943e472b10bb08ef201889d4b0d8efd437230c766afd2724f75cb90e` | `bedb28c0d21e67f2eec2c8b570e79ceda5098e05ffde2853f6ec9e395aba78a3` |
| `20261109T064444Z-ee234028e04578e923c10969b239c41c272e259e` | `c277a511c4feace32df88e9e9a65627372ceac2cbee6a4e100393a2ad46b1031` | `36b76402db0214cb66995168db2ccc39cf87a5dccf55538456571540f2053c17` |
| `20261109T064827Z-0ddc7ec6485aa3b373934dea1a4daccec87b6490` | `be4d3bf38e6c64ef89ac84a6c4c77bff3533bc959c96a5a02ae6834e82006b06` | `342d63bc08b549db252094dbec1877bb72183a0e19d308d67c160ea9feb62afb` |
| `20261109T065929Z-18b79112fafa55cf4a318585328fefa079c6481a` | `1df0e5a7bb56111c1e8449188d6987fa5373c9aab4938477929b89affff67ead` | `20568aba4a40a346a35a87169979ebf4c58d24d4954358d9cdbe2acfea86c619` |

## 容器与剩余边界

本轮未改Dockerfile、锁、部署、entrypoint、容器harness或仅容器可证明的边界，A容器构建集中E最终候选。最后已验证镜像仅为S4 handoff的历史来源线索，本轮没有取得当前候选镜像GO或carried。A通过后再进入B；最终六包/Compose与已确认最小t1仍按最终实际闭包和退出条件执行，不推送、不提前标记exit。
