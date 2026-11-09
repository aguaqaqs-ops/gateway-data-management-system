# Phase 6 S5 A 交接

当前状态：修后候选`c1a5332a8722d3736280d8b60059944e329b8697`源码CODE_GO，06复验进行中，**证据尚未通过，B未启动**。设计CLEAR、源码CODE_GO与实际验证分别记载。

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

## 容器与剩余边界

本轮未改Dockerfile、锁、部署、entrypoint、容器harness或仅容器可证明的边界，A容器构建集中E最终候选。最后已验证镜像仅为S4 handoff的历史来源线索，本轮没有取得当前候选镜像GO或carried。A通过后再进入B；最终六包/Compose与已确认最小t1仍按最终实际闭包和退出条件执行，不推送、不提前标记exit。
