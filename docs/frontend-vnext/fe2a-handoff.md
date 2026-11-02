# FE2a handoff：差异浏览

## 1. 候选与审核范围

- FE2a 起点仍记为 240d83a2711cd99f1a2be01b3f9852c4b264be1a。按设计会话要求，/home/dev/gdds-fe 的本地 main 已从该点快进到 7d6d8ad69d；该快进只更新 docs/frontend-vnext/fe2-kickoff.md。
- 代码候选：764d9527579ee121d2021ad28df74553e742a5ed；frontend/ tree：48b57c187eab142f38bbace70e382c45842ce28f。实现提交按主题拆分；本文为单独 handoff 提交，代码 tree 不变。
- 审核范围：fe-fe1-exit..<本文所在 handoff 提交>。本文所在提交的精确 SHA 见提交历史及最终回报。
- 05 调试 worktree：/home/dev/gdds-fe-fe2a-764d952757-05；04 阶段退出 worktree：/home/dev/gdds-fe-fe2a-764d952757-04。两者均 detached、clean，HEAD 与 frontend tree 与上列候选一致，均建有 legacy 符号链接。
- FE2a 未连接真实 backend；Playwright 通过 route interception 提供模拟 API 与 bundle tar，不需要节点占用标记。没有改动 vnext/ 后端代码或接口。

## 2. 完成情况

### FE1 带入项

| 项目 | 完成情况 |
| --- | --- |
| N4 | OPFS bundle 的 manifest 与 closure 在打开时验证；产物在每个打开会话首次读取时验 SHA-256，并缓存已验证路径，后续读取不重复扫描整文件。完整性失败会移除该 bundle 并走重下载路径。 |
| N6 | 应用 tsconfig 不带 Node 类型；测试使用独立 tsconfig。浏览器类型隔离检查确认应用代码无法解析 Buffer。 |
| R4 | 本地搜索跳过 ArrayBuffer/ArrayBufferView 字节和 kind 等结构字段，只搜索展示文本/值；补有二进制标识和 kind 不误命中的测试。 |
| 行分隔色 | 表格行分隔线采用 #EEF1F4。 |
| D1 | surface 导航投影通过 diagnostics_ref 解析导航诊断；导航诊断文案表与目标节点呈现已实现；移除 diagnosticText。 |

### FE2a §5

| 范围 | 完成情况 |
| --- | --- |
| 5.1 模式与页面 | 单工作台支持 Preview、审核、History 两节点与 History 三节点浏览；顶栏两行，模式操作区保留空位，FE2b 写操作按钮未接入；Loading 骨架与可重试错误页完成。 |
| 5.2 侧栏 | 采用方案 A；业务导航存在时按分组/节点/页签构造，缺失时回退为单组；搜索、只看变化/风险过滤、折叠宽度与展开状态、本地持久化和当前项可见性完成。页签与溢出可浏览。 |
| 5.3 表格 | 按 S4 呈现行类型、修改行连线、相邻关系失效时的符号回退、可展开的未变更折叠行、原行号、风险整行底色与左侧色条、单元格变化强调、未变更风险行、变更定位与分布条、表级状态、ordered 与 blank 记录。Debug 显示原始 record_kind、修改对的 Row Role“前/后”、ordered semantic_kind 与位置；删除 Change Group。 |
| 5.4 公式 | composite_signal_point 公式抽屉完成。Preview 只显示上传侧，公式变化标“公式已改”并说明改前公式在 BE-b 后提供；History/审核并列显示两侧并标出变化。 |
| 5.5 诊断 | surface diagnostics_summary 按文案表映射已知编码、未知编码使用通用提示；导航诊断经 diagnostics_ref 展示在关联目标上，不使用风险色。 |
| 5.6 视图与 URL | 去掉写死的 ViewKind，使用 bundle 自带视图 ID；视图、模式、bundle 摘要、节点、页签、变更序号、仅看差异、Debug、搜索写入 URL；刷新恢复同一浏览状态，当前本地 bundle 可复用。 |
| 数据集替换 | 显示 identity_pairs 结论并支持双侧浏览，不合并为普通差异；确认操作保留给 FE2b。 |

## 3. 后端生产 fixture

生成器是 frontend/scripts/generate-backend-bundle-fixture.py，使用后端生产 pipeline，不手写或改写 bundle 风险产物。生成和复现均在 ct108-gw-dms-05.lan 完成，gateway-backend-deps 依赖镜像、Docker network none；未启动 Dolt/Compose。

- 生成器来源候选：5c3899ce9bd29956621a8d9a5854831445b456ea；frontend tree b3c8394141b166105746d5377ee031bdc2fb018d。
- 后端来源提交：c1a76ea345f3b183cc9b04a2e90d3f58257626d7；vnext/ tree 2791d3ff3dd62ff454d7e9cac43885d39da8bf96；backend uv.lock SHA256 d18d89a24a8acae02eb6b3b23c342c1b673ea0e7e87add93d0762edfa18b822d。
- 导航投影和导航诊断仍按 BE-b §4.2/§4.7 由前端输入构造：business-navigation.json SHA256 fef43f6e1fbee8e8cf0b9882fbe0469ae3219749bdfb7f408a9c94b88f284127；navigation-diagnostics.json SHA256 c0d4b157580f8b428b2e8bb9c63b78a4bfe6a4bcb51c65a0f6ac2cfd81d2f791。通过 SurfaceProjectionRef（含 diagnostics_ref）注入并进入 closure、bundle digest 与跨实现摘要测试。
- 复现命令（在上述源树和预填充后端依赖环境内，输出目录需为空）：

    python3 frontend/scripts/generate-backend-bundle-fixture.py \
      --output-root <empty-output-dir> \
      --navigation frontend/src/test/fixtures/source/business-navigation.json \
      --navigation-diagnostics frontend/src/test/fixtures/source/navigation-diagnostics.json

- 两次生成各输出 198 个文件；reproducibility 日志 byte_identical=true。生成日志 SHA256 分别为 ee9f7a03d56b0dde89e1d7e5499c06b51873943b3e85295c91246bd94a86564a、aa3f8139a82610a28f5a01528b9a3a18d99cbcebdeb60b8c8d767fa449ecf3dc；逐字节复现日志 SHA256 26d1a3c7f564bb5760cb171386b220d6561f9532bd586803698ec0a0d013797e。汇总日志 SHA256 9b6cd02a04e6e1e36d672b4e1508740d54b3f697bd137de97eba66ca6793c696。跨实现摘要由 frontend/src/features/bundle/backend-fixture.test.ts 对全部五个 bundle 覆盖。

| Bundle | 实际风险等级 | bundle digest | closure digest |
| --- | --- | --- | --- |
| Preview FULL | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN | sha256:992e72e3b42356ab347ab5c76fd91c13d40e36340101f3602c68562947b824df | sha256:18039aff50bc21397ad19f7a7a119515b8b06d197b9f9307798e379cb7debf67 |
| Preview MODIFIED_ONLY | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN | sha256:885457cfbe2f5838f524f40906d1407bf018fed77a57838ea3d4a332ca4c5132 | sha256:ae6989ec1f75ee4107d8828dfdaf59d9ca87b792df809ba604b48674c6e0564c |
| Preview 数据集替换 | HIGH | sha256:797beec65dc753ed0bd24ea132bbdb1a22f460cab88bf4cd143eb6244a18fe99 | sha256:ad330cdbfebe0b60a78a174e84442b51723d750d18aaad0a55a4bb77588a0308 |
| History 三节点 | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN | sha256:7eaf813c7d0b7ed4ff8c592b60ae2389491a57d7f611eac1ae749ecf7ba9d186 | sha256:26edf1ab40fbee3be02c9f54851333d792b61c16ea7658ab1a7f2c89978ef23f |
| Preview 无导航产物 | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN | sha256:10c8433a2c4ad3c1ebceb46ba29d30e93c6ea8bc3836615e411649084faf952e | sha256:49c8fdadf1b71a9515c88bafbc456bfd374615c3f597d6f2e1c636bf1d10dcc8 |

### v1 不产出项的覆盖方式

按设计会话 2026-11-02 对 §7.1 的补充执行：

- 风险规则固定为 V1_RISK_RULE_SPECS。生产 bundle 只保留对应输入下实际生成的等级；没有注入或改写风险产物。
- LOW、行级 HIGH/UNKNOWN、未变更行风险的渲染测试输入来自解析后的后端 annotation 对象；测试复制对象后只改 risk_level 或目标行标识，不手写对象结构。这些副本只在渲染单测中使用，不进入 bundle、closure 或跨实现摘要测试。
- 五级颜色由 S4 semantic-tokens 截图验收。S4 grid-main 未显示的等级按 kickoff §7.1 记作已知差异。
- FAILED 表级状态未通过合成 bundle 覆盖；渲染测试以解析后的后端表对象为源，仅替换 changeKind，验证失败提示。
- keyless_demo 的 v1 结果是 DEGRADE_NO_COMPARE_KEY、零行差异和 surface DEGRADED，不是 KEYLESS_FALLBACK。该结果按 v1 原样留在 bundle；前端按诊断映射显示，不伪造后端产物。
- Preview 改前公式需要 BE-b（FE4）能力，按 §5.4 只呈现上传侧；不为补齐该数据手写 bundle。

## 4. 测试与运行证据

05 与 04 都在 clean、已提交 detached worktree 调用 frontend/scripts/run-tests.sh --screenshots <worktree外绝对路径>。runner 使用固定 Playwright 镜像与预填充 npm cache，Docker network none，npm ci --offline。完整链路包括 typecheck、浏览器类型隔离、ESLint、Vitest、production build、dist 字符串检查与 Playwright e2e。

- 05：gw-dms-test-05.lan；2026-11-02 23:48:23–23:48:43 UTC；worktree /home/dev/gdds-fe-fe2a-764d952757-05；起止 HEAD 均为 764d9527579ee121d2021ad28df74553e742a5ed，起止 frontend tree 均为 48b57c187eab142f38bbace70e382c45842ce28f；exit 0。13 个 Vitest 文件、61 tests 通过；Playwright 4 项通过；production dist 检查确认不含 simulated API 或身份选择代码。runner 日志 /home/dev/gdds-fe-logs/fe2a/frontend-tests-20261102T234822Z.log，SHA256 79f35505c10e6008c4ddf852e9aebe4de844a912400f2fd887366ee2c0682a78；包装日志 /home/dev/gdds-fe-logs/fe2a/frontend-tests-764d952757-05.log，SHA256 ec7b0d9d732672a1136d059fd423abff7e7cb0052d52abc39c2cf6ecdb69bca3。
- 04：gw-dms-test-04.lan；2026-11-02 23:49:19–23:49:42 UTC；worktree /home/dev/gdds-fe-fe2a-764d952757-04；起止 HEAD 与 frontend tree 同上；exit 0。13 个 Vitest 文件、61 tests 通过；Playwright 4 项通过；production dist 检查通过。runner 日志 /home/dev/gdds-fe-logs/fe2a/frontend-tests-20261102T234919Z.log，SHA256 f340f225c2ee47ea09a761cb6e66e12aee6b9eca8c95a73e8ac23ae625d18c96；包装日志 /home/dev/gdds-fe-logs/fe2a/frontend-tests-764d952757-04.log，SHA256 4b1b64ceded05b0605fd3a85ae4edc08a5f304dbbc873b0404afc0222a5dc85e。
- 两次完整 runner 中 browser type isolation 均确认 Buffer 不可用于应用代码；production build 均完成。build 输出存在 Vite 的大 chunk 提示，不影响构建或 dist 检查。

### 工具链与缓存身份

工具链和 npm cache 延用 FE0 预填充，本轮未改依赖、未重新传输。跨节点以 config digest 和全部 DiffID 核对，没有比较 docker inspect ID。

- Playwright 镜像：mcr.microsoft.com/playwright:v1.64.1-noble；config digest sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017；docker save archive SHA256 5babfc35ed51468126d75d5996e4f744a4e58f5442a2a3bb0135630379be163c。
- Playwright RootFS DiffID（顺序保持镜像层顺序）：
  1. sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278
  2. sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07
  3. sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9
  4. sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d
  5. sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc
  6. sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5
  7. sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb
- 该镜像来自 CT201 的 FE0 预填充。05：2026-11-02 08:11:34–08:12:51 UTC 传输、load 与身份核对；04：10:26:52–10:28:19 UTC 传输和 load。FE2a 沿用既有镜像。
- npm cacache 归档 SHA256 0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4；npm cache 来源提交记录为 a2fb4a027a6f62218109783674cfc37bd64e14a5，lockfile 有 305 个 resolved 项。05 路径 /home/dev/gdds-fe-cache/fe0/npm-cache，04 路径 /home/dev/gdds-fe-cache/frontend/npm-cache。原始 CT201→05 预填充和校验为 08:14:24–08:14:51 UTC；04 为 10:29:01–10:29:22 UTC。FE2a 未重传缓存。
- 后端依赖镜像：gateway-backend-deps:lock-d054366c02fa；来源 FE1 CT201 build，输入来源提交 c1a76ea345f3b183cc9b04a2e90d3f58257626d7；归档 SHA256 a9dc6673c1089724859ed1ea7b726af6219aa136dee8b59a5ad961c3d9e32720；config digest sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a。identity_match=true。身份解析脚本 SHA256 c205c3c044d388ce7a75f36eb4d02ef209b4487ef4d2f39229d4abc98f179a45；05 身份 JSON SHA256 0c1d87ef97a48c5b1067a231407322a39d6d5d4f6912f2beba8cbcfe866249a8，核对日志 SHA256 39fac1abfed102d422a95372711c5eb12903b156773bb56c995d6f5b94d777d0。FE2a 沿用镜像，没有重建或重新传输。

后端依赖镜像全部 19 个 RootFS DiffID：

1. sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a
2. sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104
3. sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15
4. sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1
5. sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a
6. sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25
7. sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588
8. sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1
9. sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1
10. sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f
11. sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6
12. sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6
13. sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce
14. sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c
15. sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3
16. sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4
17. sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814
18. sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
19. sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0

## 5. 截图证据

04 截图均保存在 worktree 外：/home/dev/gdds-fe-evidence/fe2a/764d952757-04。共 30 张 PNG，每个状态覆盖 1280 与 1920 宽度，runner 记录该目录路径。下表按文件 stem 分组，列出 SHA256。

| 状态 | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- |
| bundle-error | d5a60c2da980e6426d0335f21dc8c63e3347c328d9dba592ccaedec18ab5dead | 58ffc6e2a78ebfd9251fcac5fb49d477fea15dcd377cb5576642f857e88885a2 |
| dataset-replacement-browse | 517067ea9bf7569fb87f0dc95a39eaf07dbf2c05ac71d5df7043699468d3e909 | 297225ff27164717f1d08bfa9c42e05418739258880180c4975c6e9ea5bf16ee |
| formula-history | 2c3dcec0ee3b955e8b4f735513d36455dafc9df637fd5c40e8b222c352577530 | d2bd708e70a0fe8eb031fec7735c5373000b6bfed77610480a2322c97c3277ec |
| formula-preview | bbb114cc82b7de2705c8d3a47e2248069084809f079266dcccf8d7d715e97964 | e1c61bfcb4b145f649691515c000347298605dcfbf5c7b2fd710e9b4aa245bb7 |
| loading-skeleton | 7f2152d3e5a93daeb4ba0368ab9dfb3400907c94b07e0d62965fe6b8cba3ee3c | 163256c14bca17de7c436f6929249784c2c5c019b7242ed24fb35d8f04eeea3d |
| navigation-fallback | dbf031faebf96c50a8cc0e597b8a74c65abfa05866d053024138998bde213546 | 35e1fe2115cfff63cdff5dd147714592a5c5d68e4dd2d939dd6f8bb396cbea5c |
| s3-header-history | ca6db55e4f82c8e2b779b5677887a0645dff4f7c627d86592ca029e3d996af15 | 429f689d068606aea05ba12704db04ad0b02384c8e0d5921c3e4968c2f2ef459 |
| s3-header-review | dd7c2abfc892e48b1fe963bebcacd346883ba9e3565c39e0119654e718929e56 | 0adb72ac0ce75c96228a7594cbac507476b8736ff252710ac8f1baa6f267e898 |
| s3-header-upload | 042d7a46531f0b5e0f92882346802c9535e5da1abbe8ba5e7e9301b0048445e3 | bfac88263e5a99037a947ca90fbfe152237b13237c2f8e606a9351a9c9d3d1c7 |
| s3-workbench-upload | ff3660e9a1b093a75f74ce5e80f02d0bf9a5e889e6cd60d8f413b7209ccdfb3c | 9288e22678cd7dd573ac69edff3a013702f4628621a757c84ceee214a2340ef6 |
| s4-grid-debug | 0b4519ae1b092200e75a0ce0d3dffeede6e48ba52b798ffd18d7a166cdb75068 | 99f152d0e1d587e2295e39d59a7acc50ffe59ca7bece21690905477ec7024d26 |
| s4-grid-hover | 3bdd1c3e55c1e00e38784b16d894efdf2f6e386a99dc9060b34a90ebc640dc59 | 3a8f65fd7e726be32c4707a24cb7311e738bb7798115548a52677cbd87b63dee |
| s4-grid-main | ff3660e9a1b093a75f74ce5e80f02d0bf9a5e889e6cd60d8f413b7209ccdfb3c | a90c00fdd9e9ec562b3bcc4f200361655d25ac867a958fee4629422a104ed34e |
| s4-semantic-tokens | 0a409d3fbe7f395d73cd6053c5997ed0af1305f11811f3e319d3f4d2f8b6d78c | 896b281e0a6f218648b497655a1702c5f109532cb38087b168e168c4a19a2cf6 |
| tab-overflow | 304aaa185ff726bd47e0fd88d11387420e144824cb0da172f67817e29872d5b0 | a8d6eae2c9767a9456ab99499f9bd8547086cf3a710d3388f3771dd52bc75cbc |

### 草图对应与无草图页面

- s3-header-upload/review/history 分别对应 S3 上传、审核、History 顶栏；s3-workbench-upload 对应 S3 工作台；tab-overflow 是 S3 的额外窄宽度页签溢出状态。
- s4-grid-main、s4-grid-hover、s4-grid-debug、s4-semantic-tokens 分别对应 S4 主表、悬停、Debug 和 semantic-tokens 草图状态。
- FE2a 涉及但无专属草图的页面/状态：公式抽屉 Preview、公式抽屉 History、数据集替换双侧浏览、无导航产物侧栏回退、加载骨架、bundle 错误页。公式查看与数据集替换均不含 FE2b 写操作或确认对话框。
- 已知差异：S3 整页截图中的模式操作区留空，符合 FE2a/FE2b 切分，不算偏差；S4 grid-main 显示生产 v1 可产出的行风险，缺少等级按 §7.1 记作已知差异；Preview 改前公式等待 BE-b（FE4）。其余草图符合性由审核会话逐张核对；实施会话不做自审或像素比对。

## 6. 取证操作记录（DC68 与中间修正）

### Source transfer 与节点准备

- 05 的两次 clone 失败日志：
  - /home/dev/gdds-fe-logs/fe2a/source-bundle-transfer-05-7b41acea.log，SHA256 1125f2e9e9379cec815c458f71c624115b71b0b9335d14d21f48cfdada190a42。
  - /home/dev/gdds-fe-logs/fe2a/source-bundle-transfer-retry-1-05-7b41acea.log，SHA256 6f6c1245e048867b0c449388d85e7c909831cb7d6639d60d6b91bfb944571fd8。
  两次均是 git clone 解析到 /home/dev/gateway-data-management-system/.git，而 05 root 的 safe.directory 仅匹配 /home/dev/gateway-data-management-system。没有修改节点 git 全局配置。按设计会话指示改用 bundle/fetch/worktree；成功记录 /home/dev/gdds-fe-logs/fe2a/bundle-fetch-worktree-05-7b41acea.log，SHA256 b8cc257a94f18c41205310b61346ccc685068296db8b983ee676feaa637546c4。标准流程 bundle SHA256 96e88948217b3bfaf2f405c9b868fb3ccef65e09b906d274df5b54e337bac8eb；在共享仓库中 verify/fetch，FETCH_HEAD 精确为 7b41aceaee05f280e09c070efaa58b008241feaf，detached worktree frontend tree 为 ef1592faf010617b48a5c7576bf8d4bb89541acd，legacy 链接存在，随后删除远端 bundle。共享仓库 main 前后均为 240d83a271，未切换或合并 main。后续 FE2a 候选也用相同 bundle/worktree 流程建立 clean detached worktree；最终 05 runner 的 HEAD/tree 记录见上节。
- 早先一次 bundle verify 命令未提供 repository，失败日志 /home/dev/gdds-fe-logs/fe2a/source-bundle-transfer-05.log，SHA256 40ddc2f40422d355ddadaa8e9cb91acc077563cdfb58e2d158b65f7d1d8ed2df；修正为从共享仓库执行 verify/fetch 后继续。
- 04 上不存在用户指定的 98dcec3a6a 前置对象，首个基于该对象的 bundle 校验在建立 worktree 前失败。失败记录 SHA256 c310142c32512a79c70bf99f4ef3f39b20a3929ec62449e79ea32b7c65016b32。改从双方已有祖先 240d83a271 生成 bundle；候选 bundle SHA256 6764dda6eb07315351e59e2c644eec5636214ead2b9f598b032987b5408597c4。fetch 后确认精确候选 SHA 和 frontend tree，再创建 clean detached worktree；未更改 04 共享 main。
- 本机对 05 日志路径做过一次无效的本地 SHA 探测，日志 SHA256 17f327feac50df2ee86dd5161232371e259df7de643b805e8646c92681c35195；按文件实际位于 05 改为 SSH 读取，取得并核对了上述原日志 SHA。

### Runner 与 fixture 中间失败

权威 runner 已开始后的非零退出按候选缺陷处理，均追加修复提交并从头完整运行；最终 05、04 runner 均绑定到同一候选并 exit 0。中间日志保留于 /home/dev/gdds-fe-logs/fe2a/。

- fixture 风险摘要曾尝试遍历二进制数据；在 5c3899ce9b 加入跳过二进制值的处理后重新生成。首次日志 SHA256 73f2e51a2561c6e6f48cf670ce510b52e96e45f6fc647f299ff957ccc36d8652；随后两次输出可逐字节复现。
- fixture/parser 与 ordered/blank 行断言按后端实际 row contract 和位置语义修正；具体实现提交见 5277d05419、c5125bc68e、d4dfe7d922。测试日志均保留在同一目录，非零后没有沿用旧通过结果。
- Playwright 初期发现预期溢出 tab 与实际 overflow 状态不符、审核旅程复用了 Preview 专属表、搜索/URL 状态用例选择了无效导航状态；分别修正为真实溢出 tab、有效审核状态与受支持的 URL 状态。
- set-bundle 的空 digest 曾保留空字符串而未回退响应 ETag，导致 bundle 错误提示缺少 ETag。89645c84ec 加入响应 ETag 解析与同路径 bundle 复用；之后重跑通过。
- 新增 FAILED 表状态渲染测试后，先修掉未使用的 DerivedTable 类型错误；Vitest 用例仍缺显式 API import，最终由 764d952757 加入 describe/expect/it 显式导入。此前两次 runner 日志 SHA256：6a46e766bc90b370c83936447225211c63060aad9e40fa37461c2132afc653a7（TypeScript exit 2）和 eeac730fc28d5437bfb205b64a564be1593dbf2c3ba0936cc82ab2e4cf02fd49（Vitest suite failure）。最终 05 和 04 完整运行结果见上节。
- 04 曾有一次外层 tee 启动时日志目录尚不存在；候选 89645c84ec 的 runner 本身完整通过，内部日志 SHA256 2e34126187af80b06ca97c1c39ac394cf9a14c59b40d8027d8431e8c4cf654c3，但外层 wrapper 日志未落盘。最终运行在 tee 前显式 mkdir，保留了内部与外层日志及各自 SHA256。

本 handoff 汇总了实施边界、fixture 溯源、两节点最终 runner、镜像/缓存身份、截图与已知差异。审核会话负责独立核对，不在本会话中自审。
## 7. FE1 带入项完成标准核对

- N4：单测确认同一浏览会话第二次读取同一产物不再计算摘要；摘要不符会清除本地 bundle 并请求重新下载。
- N6：独立一次性类型探针验证应用代码使用 Buffer 时 typecheck 失败；测试和构建脚本使用独立 Node 类型配置。
- R4：单测分别验证搜索“12”不命中只在二进制行标识出现的字节，也验证搜索“string”不命中值结构中的 kind。
- D1：business-navigation.json 不再内联 diagnostics；SurfaceProjectionRef.diagnostics_ref 指向独立产物；移除 diagnosticText。单测覆盖 v1 导航诊断 code 文案、占位符与 params 对应关系、未知 code 的“导航提示（{code}）”以及 diagnostics_ref 为 null 时不显示诊断。
- 行分隔色：S4 grid 截图以 #EEF1F4 验收。

5.3 的单测还覆盖修改行配对/折叠推导、仅看差异保留未变更风险行、变更分布与定位、侧栏过滤；界面保留 W7 可读化、W8 复制入口和 X5 焦点样式。

### bundle/fetch/worktree 命令记录

05 首个成功标准流程以 98dcec3a6a 为共享仓库已有基线，传送 fe-vnext 候选后执行：

    git bundle create /home/dev/gdds-fe-logs/fe2a/src-7b41aceaee.bundle 98dcec3a6a..fe-vnext
    scp /home/dev/gdds-fe-logs/fe2a/src-7b41aceaee.bundle ct108-gw-dms-05:/home/dev/gdds-test-tmp/
    cd /home/dev/gateway-data-management-system
    git bundle verify /home/dev/gdds-test-tmp/src-7b41aceaee.bundle
    git fetch /home/dev/gdds-test-tmp/src-7b41aceaee.bundle fe-vnext
    git worktree add --detach /home/dev/gdds-fe-fe2a-7b41aceaee-05 7b41aceaee05f280e09c070efaa58b008241feaf

FETCH_HEAD 与 worktree HEAD 均核对为 7b41aceaee05f280e09c070efaa58b008241feaf；完成后删除节点上的传输 bundle。
