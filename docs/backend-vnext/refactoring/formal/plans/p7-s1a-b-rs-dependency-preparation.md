# S1a B RS独立配置依赖准备固定稿

本稿只描述本候选依赖准备；须同一原审核准精确clean候选、脚本及SHA后，由唯一测试角色操作。未构建、未预填、未签SCRIPT_GO/EXEC_GO/B_GO。CT201只做依赖制品准备，不运行产品lint/mypy/pytest/编译；脚本语法与Python AST检查由唯一测试者在06执行并保留独立原件。完整产品验证仍只在06。

## 修订与锁来源

RS既有distribution owner禁止import shared kernel。本候选去掉该边，只新增`rfc8785==0.1.4`精确production依赖；不改变repository三distribution依赖边，不放宽类型。库有py.typed。BE继续消费shared kernel；两侧共享完整JCS preimage/SHA与Unicode/I-JSON边界向量，不用`json.dumps`替代生产JCS。当前旧6dc与新b47锁的唯一语义差异须由准备脚本在运行时严格证明；其余所有包、来源、版本、marker及metadata不变。

CT201实施时两次`uv add --directory vnext/repository_service --no-sync --offline 'rfc8785==0.1.4'`退出1，原因是httpx2的解析metadata不在对应cache（不是06缓存缺失/产品重试）。第一次直接uv继承ambient index，第二次通过`source vnext/scripts/lib/gateway-index-env.sh`后`gateway_invoke_uv 0 add ... --offline`剥离index/config；两次均未sync环境。两次原stdout/stderr/exit仅存在工具会话原记录，没有独立实时日志文件及SHA；开始/结束时间未知，不能补造。失败后只读`git diff -- pyproject.toml uv.lock`为空的工具记录可见，但没有独立快照SHA，不能写成独立无漂移原件。随后在可联网CT201通过同一`gateway_invoke_uv 0 add --directory vnext/repository_service --no-sync 'rfc8785==0.1.4'`成功（exit0，Resolved37packages）；仍没有独立实时日志文件/SHA。Git可审diff仅加rfc三处，新lock SHA `b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f`，canonical PyPI registry保持，production Docker ARG同步。新wheel尚未获取；以下批准后的curl才产生独立下载/SHA原件。

新wheel为锁中canonical URL：`https://files.pythonhosted.org/packages/4d/78/119878110660b2ad709888c8a1614fce7e2fab39080ab960656dc8605bf6/rfc8785-0.1.4-py3-none-any.whl`，SHA256 `520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48`。版本与shared-kernel既有精确依赖相同，但仍核制品完整SHA。

## 输入与构建模式

新tag固定`gateway-p2r1-repository:lock-b47d6de3cbce`；旧tag `gateway-p2r1-repository:lock-6dc9659f0aee`保留。采用官方RS预置环境模式的窄增量：从已核6dc dependency-base保留完整/app/.venv，仅offline/no-index/no-deps安装精确wheel到该环境，替换镜像中的锁副本；不会装shared kernel，不同步/下载其他包，不装service root。runtime Dockerfile仍COPY当前contracts/src、当前service/src并用原PYTHONPATH；预置分支跳过uv sync，所以本稿必须先证明完整新环境满足锁，不能只靠新label或pip check。

精确可信旧来源见[p7-s1a-b-rs-base-source.json](p7-s1a-b-rs-base-source.json)。其中06原件路径/SHA及精确ref来自原审R12；config digest `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`与全部16有序DiffID逐项列出。CT201当前inspect不作为来源证明：脚本先实际docker save当前旧tag，从唯一Config原bytes算SHA、比完整DiffID；不等即停，不load/覆盖旧tag。最终新镜像DiffID还须以这16项为前缀，防构建窗口base变更。

[p7-s1a-b-build-rs-dependency.sh](p7-s1a-b-build-rs-dependency.sh)固定三参数：`B_SHA CLEAN_CANDIDATE_WORKTREE NEW_OUTPUT_DIR`。只接受hostname heavy-dev-01、精确候选clean/source中本脚本、全新输出路径；新tag及本人容器名已存在即停。原审批准时将参数固定为实际40位候选、`/home/dev/gdds-p7-s1a-b`（执行期间实施者不写）、全新`/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3-build`。开始前只读确认该输出路径未被占用；不覆盖任何旧产物。

步骤固定为：旧/新锁TOML严格delta证明→旧base save/config全层核→旧环境完整元数据→CT201下载精确wheel并核SHA→官方repository build identity helper获取本clean候选真实revision/source-tree→记录完整dependency-input.json及SHA→network none/pull=false构建唯一新tag→新环境逐包验证→旧/新元数据只差rfc严格比较→pip check与Dolt2.1.11/uv0.11.28→save新镜像，原Config字节、完整有序DiffID、新labels、archiveSHA形成image-identity.json。

环境核[p7-s1a-b-rs-environment.py](p7-s1a-b-rs-environment.py)只读importlib.metadata，沿root所有production+dev依赖递归并按当前平台markers选边，核每个适用第三方分发的锁定版本；contracts必须editable、direct_url=file:///repository_contracts、.pth对应`/repository_contracts/src`，旧新元数据一致。根service明确不要求安装，最终runtime供应/app/src。若旧来源editable路径与此前实际预置模式不一致，脚本停止交原审，不能现场改path凑通过。

真实labels重新记录：candidate revision、官方helper build-input-revision/source-tree、dependency-input完整SHA、当前lock、Dolt/uv/mysql-connector/PyArrow版本及cache-policy；不能继承旧revision/tree冒作新来源。recipe见[p7-s1a-b-rs-dependency.Dockerfile](p7-s1a-b-rs-dependency.Dockerfile)。backend五输入没有变化，原578不构建/覆盖。

日志build.log保hostname/起止UTC/HEAD/clean/每步原exit；每个end命令非0逐项聚合，INT/TERM以130/143明确进入失败收尾，tee等结束后SHA，主体/日志exit分别记；所有context、下载、旧/新tar、JSON原件与新tag保留。docker run均network none/read-only且--rm；每次run以全新CID文件记录实际创建ID并标记唯一invocation=$out；若有残留，仅在本次记录CID及精确candidate/invocation/name证明后按CID移除，前置碰撞不触碰既存容器。成功容器清单为空才认absent，ls/inspect/归属/rm/确认任一失败或未知均非0；来源tag/他人容器不动。失败停交，不自动重试/删产物/换tag。该元数据与工具核是依赖准备，不是产品测试通过。

## LAN与06准备（实际SHA回审后才可执行）

构建成功后先由原审核收真实完整原件/SHA，再固定以下传输清单：dependency-base.tar、image-identity.json、dependency-input.json（另交原build.log/SHA与来源证据）。在06建立全新`/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3-incoming`，不复用、覆盖或删除他人路径。由唯一测试者经获准LAN SSH/scp从CT201准确新输出路径传入，记录双方hostname、起止UTC、原numeric exit、传输前后SHA；只传固定制品，不打印凭据、不走公网/转发代理。06 LAN源码仍用本候选完整Git bundle，clean detached source与legacy按单独固定准备包建立。

[p7-s1a-b-prefill-rs-dependency.sh](p7-s1a-b-prefill-rs-dependency.sh)固定五参数：`B_SHA CLEAN_06_SOURCE ARCHIVE_SHA256 IDENTITY_SHA256 DEPENDENCY_INPUT_SHA256`；后三值现在UNKNOWN，只能从成功build原件由原审核收后写死进外置调用稿，禁止占位符执行。脚本只接受gw-dms-06与精确clean候选，新输出根`/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3`、archives与日志首次创建。取得本人的整机标志，现场核无Dolt/Compose/8000冲突、本机Unix Docker、无proxy/endpoint覆盖；新tag/本人容器名碰撞即停。

先核LAN输入三SHA、candidate/lock/完整source claims及tar唯一Config原bytes/全DiffID/labels，与已核旧16层前缀相同；只load该新tag归档，保留旧6dc。再save当前新tag、逐项比source config/fullDiffID、完整labels，重复完整锁环境元数据/pip check/工具核。archives保三固定输入、当前重导出tar及SHA。

06 host uv cache是另一前提：本轮先前shared-kernel成功offline sync已实际消费同版本rfc8785，但不把这推定为新RS锁完整缓存通过。准备脚本在新clean source用受控入口`UV_OFFLINE=1 ... uv-consume.sh -C vnext/repository_service sync`实际核本机新锁缓存/环境；不公网取包、改index或改锁。若任一cache缺失，原exit停止并保新镜像/全部状态，先经独立已审CT201→LAN预填方案补齐，不从本步骤重试。正文以后仍从完整开头同步五包，不能把准备sync或旧静态通过拼成产品通过。

prefill.log独立保存hostname/起止UTC/HEAD/clean/原exit与SHA；每个end命令非0逐项聚合，INT/TERM以130/143明确进入失败收尾，tee/主体分别exit；容器同样由每次run全新CID文件和本次invocation证明；容器query/inspect/owner/rm/确认失败或未知时非0并保留busy。仅确定本次容器已清才按精确owner内容guarded释放本人marker，全部文件/新旧tag保留。LAN/导入/重导出/host uv准备均成功后，原审核收实际原件，外置正文wrapper写死identity SHA再给EXEC_GO。此时正文为五参数`B_SHA CLEAN_SOURCE NEW_LOG_DIR SESSION RS_IDENTITY_SHA256`，固定选新b47base；原578身份早停不变，五包静态、既有focused及History Compose范围完整保留，新增既有independent-package owner selector。未得到实际SHA/EXEC_GO前不调用正文，不移动已审候选来补文档。
