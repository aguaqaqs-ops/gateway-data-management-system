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

## 8. 定向修复第 1 轮

### 候选与边界

- 本轮开始前，/home/dev/gdds-fe 的本地 main 已 fast-forward 到 2e7428a5e5；按 FE2 kickoff 当前版本的 §4.2、§4.3、§5.1、§5.3、§5.5、§5.6 和设计答复执行。fe-vnext 没有合入这些文档提交。
- 代码候选：2b62bf21a09f9cde69528eb520cdc5f6296a9486；frontend/ tree：26003bda196bdc16f17ff22767943f0b4f94d153。
- 审核范围：57e77505f6c79752a7abd5f8df5deeb7080b19a0..<本节所在 handoff 提交>。代码候选提交至 handoff 提交之间只有本文件变化；handoff 单独提交，frontend tree 保持不变。
- 本轮只修改 frontend/ 和本 handoff 文件；未改 vnext/、AGENTS、kickoff、UI 优化方向或审核报告；未推送、打 tag 或合入 main。
- 修复提交：ce0efc3c22、fc8dd49a84、cdda7d6fc8、6d2d338ab8、789070db2a、a3233b91fe、11fa9c5b22、26ceed468e、83ce1d53fb、29010385a8、9ba9ecf70c、2b62bf21a0。

### B1–B9 与 R 项

| 项目 | 修复方式 | 代码提交 | 测试 owner |
| --- | --- | --- | --- |
| B1 生产 fixture | composite_signal_point 通过生产 materialize_business_snapshot，以输入 SQL 和 logics.xml 合成；公式使用真实 EXPRESS/POINT/DIGITAL AST，覆盖嵌套命名表达式、连续同类或运算链与乘运算链、单子节点空操作符、一元操作符、可映射与不可映射 POINT 名称及公式变化。Preview 按生产 pair_specs、BundleInput、身份评估及 identity_before_table_set 取值；两个 pair 的 view_id 均为 initial_to_modified。History 使用固定 operation_id fe2a-history-fixture、pair_id 后缀 -p0/-p1、生产 BundleInput 节点标签及 include_all_tables。替换场景使用 Preview 生产 pair，不再造 replacement_pair。 | ce0efc3c22、fc8dd49a84 | 生成 fixture 的跨摘要 owner 为 frontend/src/features/bundle/backend-fixture.test.ts；相同 view_id 下按 pair_id 切换并从 URL 恢复由 frontend/src/features/view-model/commands.test.ts 负责。 |
| B2 公式查看 | 以可读公式行显示 AST；连续同类或运算链与乘运算链压平、空操作符单子节点展开、POINT/DIGITAL 保留原值、一元运算符前缀显示；命名表达式标题带父运算符；POINT 以同侧 device 表映射，未映射保留输入值。差异行使用底色和左边框。History/审核对照两侧并对齐变化行；Preview 仅展示上传侧并标公式已改，注明改前公式在 BE-b 实现后提供；删除测点显示记录中的基线值。入口只在 composite_signal_point 公式列单元格。 | ce0efc3c22、6d2d338ab8、26ceed468e、29010385a8、9ba9ecf70c | frontend/src/features/view-model/formula-view.test.ts 与 frontend/e2e/workspace-shell.spec.ts；E2E 检查公式文本、单元格入口和 Preview/History 抽屉。 |
| B3 行定位 | 自校验按实际快照侧逐侧验证新增、删除、修改记录，拒绝重复行身份和重复归属；任何行级定位失效或不支持的类型使整表回退表级。ROW 与 ROW_PAIR 风险标注按身份字节对应；修改记录的 ROW 标注也按 row_identity 定位。Preview 无改前快照时，删除行取 before_values；修改前行只填比较键和 before_values，其他值为空；缺失侧行号留空并说明原因。删除行置于表末，按有序表位置定位。 | ce0efc3c22、6d2d338ab8、789070db2a、a3233b91fe、11fa9c5b22 | frontend/src/features/view-model/table-rows.test.ts 的唯一 fixture owner 覆盖五个 fixture、每条行级记录的快照侧、Preview 删除/改前行、篡改身份退回、未变更 ROW 标注匹配与失败退回。 |
| B4 整表新增 | 整表新增/删除直接按 table-level 状态构造，不再把新增表内容重复走逐行新增逻辑。 | ce0efc3c22 | frontend/src/features/view-model/table-rows.test.ts：added_table fixture 是整表新增行数及类型的唯一 owner。 |
| B5 诊断 | 表诊断只进入该表信息行；pair 提示按 view 汇总减去本 view 全部表诊断的并集，置于顶栏提示条；无提示时不显示。页签悬停使用“n 张表有比较提示”。文案按 §5.5 完整映射；匹配按完整编码、冒号前缀、异常类名归内部错误、通用提示排序。DEGRADED 取文案顺序第一条，空原因显示“降级原因未提供”。 | ce0efc3c22 | frontend/src/features/view-model/diagnostics.test.ts：文案编码集合、五个 fixture 的非通用文案、无诊断 device 表、匹配优先级及表诊断不泄漏到 pair 提示；移除 DEGRADE_NO_COMPARE_KEY 通用文案断言。 |
| B6 视图风险与身份 | 页签从 surface.view.risk_level 展示风险和 S3 状态；缺失身份评估显示“项目身份评估不可用”，不再默认不同项目。 | ce0efc3c22、fc8dd49a84 | 数据集替换 HIGH 风险可见和身份结论由 frontend/e2e/workspace-shell.spec.ts 负责；缺失身份 copy 由 frontend/src/features/view-model/identity-copy.test.ts 负责。 |
| B7 变更文案 | 导航徽章、信息行及悬停提示共用 §4.3 的 SurfaceChangeKind 映射，覆盖新增、删除（数据值删除线）、更新、失败、替换；业务等价不显示徽章，悬停为“内容写法不同，业务含义相同”。导航回退侧栏复用同一映射。 | ce0efc3c22 | frontend/src/features/view-model/table-state.test.tsx 的九种 SurfaceChangeKind 单一映射用例。 |
| B8 截图与草图 | 移除模式页签，保留 URL 模式入口；删除“切回 Preview 请求数加 1”断言。截图前等待网格首格内容、canvas 与绘制标记可见，公式截图也等待表格完成绘制；重新生成完整 30 张双宽度截图。 | ce0efc3c22、26ceed468e、83ce1d53fb、29010385a8、9ba9ecf70c、2b62bf21a0 | frontend/e2e/workspace-shell.spec.ts 的 4 个 Playwright 用例；本节截图表及审核会话逐项对照。 |
| B9 死代码与 R4 | 删除应用未调用的 filterChangedRows、applyNavigationRowFilter 和对应旧用例。R4 改为通过 buildBrowseRows 的 displayRowSearchText 搜索路径验证：包含 0x0c 的行标识搜索“12”不命中，二进制值搜索“二进制”不命中。删除 check-browser-types.sh 和 runner/package 对应步骤；N6 以审核报告 §3.3 的类型探针结论为依据。buildBrowseRows 仍保留实际导航 row_filter 所需的行过滤。 | ce0efc3c22 | frontend/src/features/view-model/table-rows.test.ts；N6 探针参考审核报告 §3.3。 |
| R3 错误分类 | loadBundle 根据 BundleIntegrityError 类型归类完整性失败，不再正则匹配错误消息。 | ce0efc3c22 | frontend/src/features/bundle/local-bundle.test.ts。 |
| R2 | 按用户要求留给 FE2b，本轮未处理。 | — | — |

### 生产 fixture 生成与复现

两次生成和逐字节比较均在 CT05（gw-dms-test-05.lan）的 clean detached worktree 执行，生成器来源为 ce0efc3c22，frontend tree 45747bb23bf5942c27e33fbefe8a81d58a487bf3；后续 fc8dd49a84 将这些生产输出更新进候选。使用已预填充 gateway-backend-deps 镜像、Docker network none。没有启动 Dolt、Compose 或访问公网。两次生成各 213 个文件，bundle 输出逐字节一致。

- 第一次生成日志：/home/dev/gdds-fe-logs/fe2a/fixture-generation-ce0efc3c22-run-1-05.log；SHA256 f7d374c4a8acdfe3cf929f1dafacb2d2a351f129b708d919e9f2e915514fffd8。
- 第二次生成日志：/home/dev/gdds-fe-logs/fe2a/fixture-generation-ce0efc3c22-run-2-05.log；SHA256 dc6c77bd4539bead488a92e05b7970d2010b241c516d0385cab9e903fe07270b。
- 逐字节复现日志：/home/dev/gdds-fe-logs/fe2a/fixture-reproduction-ce0efc3c22-05.log；SHA256 311c21096e17a3a07c80fdee8455b173390d5d35579f295c8386b376c3f6bade；byte_identical=true，213 files each，exit 0。
- 两份生成摘要日志 SHA256 均为 6f858c2a20fad3bde26990b0eda3b4c87c09aeda96e78012f5a53d1b3e408aef；摘要纠正后使用 grep 查询。首次试图调用未安装在 CT05 的 rg，操作日志 SHA256 504f40400e1cfe09019c290a5a46b45b3eba6857c9c82bed03359fe0f1cbaa1f；生成器已 exit 0，未触及被测对象，该步骤改用 grep 后完成，作为 DC68 命令环境修正记录。

| Bundle | bundle SHA256 | closure SHA256 | 实际 view 风险等级 |
| --- | --- | --- | --- |
| Preview FULL | 09562cbb7bb6d26c2d5e922c43c81148732f66e4c0d77b05a4abe268911f5bf0 | 997403f2ca2b8141976be46ad382f2e84a5d13dfecfa81083377920887562bee | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN |
| Preview MODIFIED_ONLY | fcc4deb6f9215fe4948343379b00ad1e40110e7d4e4149d72ce91141a94cf177 | e9ab96623fcd8798c7c0456b13172aba48f92cee5366f132b8d6de34fc21e2d1 | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN |
| Preview 数据集替换 | f60eb9d2e4cf1c8d85e35fecbd5214335ddf11d4eaece37293c13cc329c43830 | a29400b56b0bde2ce17d1ebbc5affe336927ccf965c1fd463104cbfee18060cc | HIGH |
| History 三节点 | 5d22992d518dfd1e95cd8d7174a91fb2dad70e04a869757bf304e438f5b60b2c | 96d252ae1d8af6018f92add47112cb709d35be835651f5f980a9474c71391470 | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN |
| Preview 无导航产物 | 22bb6fdf8e54e5eb4154aa83ac4e7db21d9894e8db417e6e01c43160445f7878 | e2bf17830b216f6a7ed9ea7c88608fdf1e15267a7a3c242167337db9e6b5d974 | MEDIUM_HIGH、MEDIUM_LOW、UNKNOWN |

### CT05 权威 runner

- 节点：gw-dms-test-05.lan。测试 worktree：/home/dev/gdds-fe-fe2a-2b62bf21a0-05，clean detached，含 legacy 符号链接。完整命令为 ./frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2a/2b62bf21a0-05。
- 开始：2026-11-03T08:15:21Z；结束：2026-11-03T08:15:45Z。起止 HEAD 均为 2b62bf21a09f9cde69528eb520cdc5f6296a9486；起止 frontend tree 均为 26003bda196bdc16f17ff22767943f0b4f94d153；exit 0。
- 16 个 Vitest 文件、70 个单测通过；typecheck、lint、build、production build 检查通过；4 个 Playwright 用例通过。
- runner 日志：/home/dev/gdds-fe-logs/fe2a/frontend-tests-20261103T081521Z.log；SHA256 271de5f1d486683af2634a94c5a36d59b5e4c6d9c9931eb2e1b0b8c2082274ce。
- 外层 wrapper 日志：/home/dev/gdds-fe-logs/fe2a/full-runner-2b62bf21a0-05-wrapper.log；SHA256 d440899ef691a5c9f0c4ee8000ccb03fd1eea271687a8acd1110d8fe80aad9b5。
- 最终候选 focused Playwright 日志：/home/dev/gdds-fe-logs/fe2a/focused-e2e-2b62bf21a0-05.log；SHA256 68f6647f71945813298bd438f9c849faba450fba3b80ad9abe2262e38914cae4；4 项通过。
- 复审通过前没有在 CT04 取证；第 4 节的上一轮 CT04 运行只作为历史记录。本轮未改 npm/Rust/backend 依赖或锁文件，沿用第 4 节记录的 Playwright 镜像、npm cache 和 gateway-backend-deps 预填充及身份。第 05 节点本地重新打包的 npm cache 副本（SHA256 `91ccf6149337b4f5a9f1c690a45ac04e8b685d224e37ef595059af7fdc979991`）不是 FE0 来源归档；解包内容与 FE0 原始归档相同，来源勘误见本文件第 9 节。

### 中间非零运行与修正

权威 runner 的失败日志保留于 /home/dev/gdds-fe-logs/fe2a/，每次修复后从头运行；最终证据只取上列最终候选成功结果。

- 候选 fc8dd49a84，2026-11-03T07:50:09Z，exit 2，TypeScript 错误。runner 日志 SHA256 ecdd88939d07bd91d9bbe6cd1ceaafc91e9917c54c7b14df80c61371373da6ad；wrapper SHA256 73f6f585ad2b93dce962ba9f6d3b2f90c8b21670b02326753f408152d479d158。之后由 cdda7d6fc8 修正。
- 候选 cdda7d6fc8，2026-11-03T07:52:18Z，exit 1，Vitest 有 6 项 fixture 行数、公式预期和有序行定位失败。runner 日志 SHA256 2281557a50f5a713190ee2436c830df1f83dbbb19eab5592c7970b60f775cd15；wrapper SHA256 778e06eaac8ac6acb018db611a19a70162792d962dcec84d3758a7eb1acfcfeb。之后由 6d2d338ab8、789070db2a、a3233b91fe、11fa9c5b22 修正。
- 候选 11fa9c5b22，2026-11-03T08:03:31Z，exit 1，Vitest 与 build 通过，但 Playwright 有 3/4 项因网格首格尚未绘制失败。runner 日志 SHA256 0e920f82f1efc40126eddb671db19eae70ec204230a6097d0053100c067b4350；wrapper SHA256 bfedf74bfff320b50b532d37d565e66b7814f352b281c4aa2d4976290b14531b。26ceed468e 增加绘制等待。
- 后续 focused Playwright 发现 Preview 直接 bundle URL 的 pair 未恢复（日志 SHA256 2d3381dac7937ea297b80564c83784530e2734d08ebace0049e9f2ae12570829），公式单击入口未打开抽屉（日志 SHA256 69854e0c4c8b61de06d314d444db057ee742c1078827e8c60f404faa9caec134；随后公式表绘制等待日志 SHA256 fd945e7926bbe724d2a68915e6cd356307d57107c5f0daf8820ac29243e169fb），并发现 History 深链接的 node/tab 丢失。依次由 83ce1d53fb、29010385a8、9ba9ecf70c、2b62bf21a0 修复；9ba9 的 focused 日志 SHA256 8a970fa728c6de56c9fe6adeaa340d87fc9911c04f7704f6ef73db3468ad6c64。最终候选的完整 runner 与 focused Playwright 均通过。

### 截图、草图偏差与无草图页面

CT05 的 30 张截图保存在 worktree 外的 /home/dev/gdds-fe-evidence/fe2a/2b62bf21a0-05。审核对照时已检查两个宽度下的 S3 顶栏/工作台、S4 主表/悬停/Debug、公式抽屉、数据集替换、加载、错误及导航回退代表图。B8 表中检查项均已修正：面包屑和模式标签、视图分段控件与“全部/仅看差异”、页签行数和徽章、信息行层级、竖向分布条、表格列宽、当前变更整行边框、数据列删除线、折叠行“展开”提示、Debug 诊断 JSON 布局。未发现尚待修正的草图偏差。

| 状态 | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- |
| bundle-error | 0526a467d679cbc3e05f55e9f3b9d2e19d972420a5695568dcc451a8ea87380f | f9589c5ca9a738662c7b13700177e7dbf9b3f0a8d815beeabe65867600f4ba3e |
| dataset-replacement-browse | 50a14262070d162cfd4434816d455841b8216d0f6e314355fd3586593f2ec38d | 7b9c036fa054cea329b98ddb56f481a59da395e16da551a98e9a9a4181089b4c |
| formula-history | d1d73555cb00f54c108a52b672f2222232667c389165f9e656c94bca1f5796cf | 24eeca90faf1a5920f41e6ca395b6098b39955b212af5339455ee5f60f2bb2dc |
| formula-preview | 6291dad532eb39a42fc556b38b73d30920e570e904e87b7f4908fce9b25af4ce | fd2782831fff05675291c2f8f9f8cae5568205534f52983e0f8e97bc57924dfb |
| loading-skeleton | 4ff0390c8d74470c46102d4703ac698d16594c8b699ca38ef352dfa41565b603 | 3bbfa585429f136ae8864109f4aafc8529e115611623290091b7ea62c61f7fde |
| navigation-fallback | 59660b7a2b273b2f4ad30a479c2169a09d7d778c70227df744dd4f804f0cff43 | 4d3f27539505a647d9fca7667369c8b9699e5e92e60256eaa91ed8b83301aea7 |
| s3-header-history | a07b53c4c61a1efbe7e06e74fe7fe7bcec3ca58fec0eba28dbed1294db600f4f | b36fddebbc44476a5dfd17ca419404882edfff79dce1821f0509ccf4ced0529c |
| s3-header-review | 0266026dc4a4fc6e5a8b3589a3141e8a5a5a31ab24d449b0efcaba0969ce06c2 | 22a22f25ad2d6957fdf43aab5596b1d80f3f31e82367ec25f3aa9b5745c9868d |
| s3-header-upload | 1c3cde7e8b09259022bf5a5e65dd0effcfb3485f95ecd55ce6dfb9bd2ee69458 | badd21872bcafdcd3111a020d63c4e2c96ebf68b7787535f70775b2e37cbc62c |
| s3-workbench-upload | eb3bf6a53317be3c72f6425cdd7a6fda103c82e7b9db8b47ba68bdb61ca0a6c5 | a7e6fcd0b8308d0c1bde7ddbdf922577afa71aa50bf3a51d9d3986610d63b0ad |
| s4-grid-debug | 75a5024130ba34e310a56c47af454d28c4a8ffb957a2946320f3bda6316dc3c3 | abe1fc85a56053f0d94e93064eacda53ba03ab50c1f973b59563937fbd196aa6 |
| s4-grid-hover | 5ac0c068325e552c74c14a69a2efd9e556d3ea3144bbef00e961d176bad5e047 | 7d9d6547c5dd441ab2877143e34557630c4b7585ce382e38ce8f957e97a375d8 |
| s4-grid-main | 595985cd0e7b10523344b1f162c717e296445e9045dfe0856fa62a8e52e5dad9 | 464d645ca8ca10d97ab770679081376fe5df5c9bc476fd638bfbdb6737ace4b2 |
| s4-semantic-tokens | 0a409d3fbe7f395d73cd6053c5997ed0af1305f11811f3e319d3f4d2f8b6d78c | 896b281e0a6f218648b497655a1702c5f109532cb38087b168e168c4a19a2cf6 |
| tab-overflow | 70279675eaf0e6d78b01aba575b27231094b2d2fce72d223172a776a7109e1e0 | e6d6e6e184508f146b410d11e7feb766161274c69bd7f095cb68ba47cd6162f6 |

另列无专属草图的页面，交 owner 看图确认：公式抽屉 Preview/History（formula-preview、formula-history）、数据集替换双侧浏览（dataset-replacement-browse）、加载骨架（loading-skeleton）、错误页（bundle-error）、导航回退（navigation-fallback）；每项截图均有上表中的 1280 和 1920 两种宽度与 SHA256。数据集替换确认流程属于 FE2b，未纳入本轮。S3 模式操作区留空按 §5.1 的 FE2a/FE2b 边界执行；Preview 改前公式按 §5.4 等待 BE-b；这些是设计已说明的边界，不作为本轮偏差。请审核会话独立核对截图并由 owner 确认无草图页面。

### 仍需 owner / 设计会话处理

- 本轮没有触发 kickoff §10 停止条件：生产后端代码可在无 Dolt/Compose 的条件下产出确定性 fixture；不需要新增后端字段或接口；公式输入与后端 AST 契约一致。
- 请 owner 审核本节截图，尤其确认列出的无草图页面。除此之外没有待定的 B1–B9 修复偏差。
- R2 按范围留给 FE2b；Preview 改前公式仍按计划等待 BE-b 能力，本轮没有改造后端接口。
- 复审通过前未在 CT04 运行或取证；CT04 不作为本轮验收证据。

## 9. 定向修复第 2 轮

### 候选与修复

- 代码候选：a80a2e93af663cda6f4f972a0840df5142df4cea；frontend/ tree：f1c238248acc72b8be33fd50bb893e7539ff4caa。
- 审核范围：c1abe10cf8f5d83e3f6ab1b0c570c60744a1515c..<本节所在 handoff 提交>。handoff 独立提交；本节所在提交只改本文件，frontend tree 不变。
- 代码提交：bd6a666be3（N1、N2 实现与 owner 用例）、813da6cd61（公式 History 测试形状修订）、a80a2e93af（测试 AST 补全为生产 fixture 根结构）。
- 本轮只改 frontend/ 与本 handoff 文件；未改依赖、锁文件、后端或 fixture 生成器；未推送、打 tag、合入 main，也未在 CT04 取证。

| 项目 | 修复方式 | 测试 owner |
| --- | --- | --- |
| N1 公式分组 | 无名 EXPRESS 子节点运算符不同于父链时新增分组行，分组行沿用父链运算符并标出子运算符，组内行按自身运算符展开并缩进一层。选择的格式为“+ （* 分组）”，组内显示“* 3”“* 测控装置:测量电压”“* 4”。公式对齐按原 POINT 名称计算；History 两侧同一分组行仍对齐，变化的操作数行成对标变更。 | frontend/src/features/view-model/formula-view.test.ts：生产 fixture AST 检查分组运算符和 depth；History 用例检查分组行及组内变化操作数的对齐。frontend/e2e/workspace-shell.spec.ts 检查公式抽屉显示分组行。 |
| N2 视图状态 | 视图状态只看 changed_table_count：无变化表显示“一致”，有变化表显示“更新”。风险徽章保持不变。悬停提示按顺序列出降级表数、失败表数和有比较提示的表数，不再把表级“降级比较/比较失败/有修改”用作视图状态。 | frontend/src/features/view-model/view-status.test.ts 覆盖一致、更新、仅有降级、仅有失败及合并提示；frontend/e2e/workspace-shell.spec.ts 检查真实 Preview 页签显示“更新”，并有“2 张表降级比较”和“3 张表有比较提示”的提示。 |
| R6 handoff 勘误 | 修正本文件第 8 节的第一次 fixture 生成日志 SHA256 与 Preview 数据集替换 closure digest；下面记录的值为完整正确值。 | 复核人可直接对照第 05 节点保留日志及当前 bundle closure。 |
| R5 连接状态 | 留给 FE2b；本轮仍保留当前连接状态呈现。 | 非阻塞，按复审报告留待后续阶段处理。 |

### fixture 与 R6 更正

fixture 输入和生产生成器均未变化，按要求没有重新运行 backend fixture 生成；完整 runner 内部重建的五个 golden bundle tar 与第 8 节的 bundle/closure digest 一致。R6 两个正确值如下：

- fixture-generation-ce0efc3c22-run-1-05.log SHA256：f7d374c4a8acdfe3cf929f1dafacb2d2a351f129b708d919e9f2e915514fffd8。
- Preview 数据集替换 closure：a29400b56b0bde2ce17d1ebbc5affe336927ccf965c1fd463104cbfee18060cc。

### CT05 完整 runner 与失败记录

- 最终运行节点：gw-dms-test-05.lan；clean detached worktree：/home/dev/gdds-fe-rereview2-fe2a-a80a2e93-05，含 legacy 符号链接。执行 ./frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2a/rereview2-a80a2e93-05。
- 开始：2026-11-03T09:05:19Z；结束：2026-11-03T09:05:43Z。起止 HEAD 均为 a80a2e93af663cda6f4f972a0840df5142df4cea；起止 frontend tree 均为 f1c238248acc72b8be33fd50bb893e7539ff4caa；exit 0。
- 17 个 Vitest 文件、72 项单测、4 个 Playwright 用例通过；typecheck、lint、production build 和 production dist 检查通过。
- runner 日志：/home/dev/gdds-fe-logs/fe2a/rereview-2/frontend-tests-20261103T090519Z.log；SHA256 17a76a49e96578082ba0d4a347ae0437824bf0baa5fdeaa41cbedb544e2d39ca。
- 测试期间 frontend tree、HEAD 均未变化。CT05 runner 使用的文件 `/home/dev/gdds-fe-logs/fe2a/npm-cache-prefilled-a2fb4a02-05.tar.gz`（SHA256 `91ccf6149337b4f5a9f1c690a45ac04e8b685d224e37ef595059af7fdc979991`）是 05 上节点本地重新打包的副本，不是 FE0 来源归档；复审已逐文件确认解包内容与 FE0 原始归档相同。权威来源仍为 CT201 的 FE0 预填充，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`，原始归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。Playwright 镜像沿用第 4 节身份，config digest 和 7 个 RootFS DiffID 均与锁定值一致；Docker network none。没有在 CT04 测试。
- 中间完整 runner 日志均保留于 /home/dev/gdds-fe-logs/fe2a/rereview-2/。候选 bd6a666be3，09:01:10–09:01:23Z，exit 1，formula-view.test.ts 的 History 用例预期分组 depth 1，测试 AST 只保留一个根子节点，实际走了单子节点展开路径；日志 SHA256 281d2562d414a51f37b5075d902c6e0200ba53f9359a197b7bf22ea61a0e9940。
- 候选 813da6cd61，09:03:29–09:03:42Z，exit 1，同一用例仍失败：首次修正补了运算符链，但测试 AST 根仍只有一个子节点。日志 SHA256 8be09f14f3b11f015d34f5a8e9b334456fa29972f26b8f4697350c76cb6c68ec。a80a2e93af 将根节点补成生产 fixture 的多分支形状（命名表达式、| 链、空操作符和一元操作符），之后从全新 worktree 从头运行并通过。两次失败均为测试 AST 形状不完整；实现未改成近似编码，runner 没有沿用旧通过结果。
- 前置缓存预检曾误用 runner 的默认 cache 路径；失败发生在测试启动之前，没有副作用。修正为本节点的 FE0 预填充路径后重新预检通过。操作日志 /home/dev/gdds-fe-logs/fe2a/rereview-2/preflight-cache-path-failure.log，SHA256 e32683e3c11acf9428eab6cc7356c5aadac3a4771b536c0df0eee89d15934181。

### 新截图与外观核对

最终候选在 CT05 新生成 30 张截图，均存于 worktree 外的 /home/dev/gdds-fe-evidence/fe2a/rereview2-a80a2e93-05。1280 与 1920 两种宽度的公式 History/Preview 和 S3 页签均已核对：公式抽屉中父链“+”分组标题与内缩的乘法链可区分；视图小字为“一致/更新”，风险徽章保留。B8 其余页面重新截图，未改动项的文件摘要与上一轮相同。

| 状态 | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- |
| bundle-error | 0526a467d679cbc3e05f55e9f3b9d2e19d972420a5695568dcc451a8ea87380f | f9589c5ca9a738662c7b13700177e7dbf9b3f0a8d815beeabe65867600f4ba3e |
| dataset-replacement-browse | fe14edb359aa77086b75a6d1e7fd3be64a83ceda81ba8c6f5dc43ce6ce513eec | 974fd1e2aae8782dc837217e3471b4e88c2c6fd4ba0aea178157b40e747520c7 |
| formula-history | 47b892650a54d8ee47b3366dd551e5b58daec7b73bfde5a840bd84882add3cb5 | 831532993e2c7a9fad8ffb0c8728be7221ca6231bb5502958bac6b053b865318 |
| formula-preview | d6aa19d3a5a1df731d3d25a93db8886ac79ccb2c90f2eef6ef46690cf087efb4 | 266f59b66390ca31a4db7fd7f5d414b2d5d7b7b463153753f440bf754d525018 |
| loading-skeleton | 4ff0390c8d74470c46102d4703ac698d16594c8b699ca38ef352dfa41565b603 | 3bbfa585429f136ae8864109f4aafc8529e115611623290091b7ea62c61f7fde |
| navigation-fallback | c3b1fec89fd5b4a28e5ab2b7a3a94d51821a99a0c614496308050e8559b5d418 | b28dcd7e18679ed185aed9a82813ddda1e9707d886143d64b85bda3d7febd17c |
| s3-header-history | 76a2bf4f77191aa8cd427b960dd58fe1ab7d7eef19295150f7bb953e2f11ce3e | a235950cd378d78cd2ecfa69587ccd3d87b67d35aa6372ad4e6c7fde5cd84802 |
| s3-header-review | 2ce4bccabf5b238d3a92eab14967a5c2b8651facfdb379dc5fd9034e2cf0b045 | e6633ca1e2bd52f579e59e871b5c36a5b3e1bf9dfe7c12d5a89933020dad1309 |
| s3-header-upload | 18537557e768e5ac5d5fbc534eab791817f37916fb7c5a3d1c541a74e8c5e519 | 482ba0237a0312f363669fb505812077d3e4fa3513e4037cdca64f405e04fa66 |
| s3-workbench-upload | 5e5f68fbf68138da68e35192dee76be216ab6c85d693e27a372aeef4b31c0e6b | b639723b2f7f767988de0c0a86bf52381223acfc49f15a200eacc9433245b0b1 |
| s4-grid-debug | d8750bb38d6945571e2ce69b24fb656e3f30409e2ec48708456060f4437ca161 | 2130a48593f6720983d1f4fe1aebc8e1107451ab6a7025a5563dfb1c4d103d42 |
| s4-grid-hover | fdca73df8306966bcf43d05b78fc8c2a1ebc068ce35e0b3297eebdd1f391ba67 | a27bf6e83c0337b2d78d4343ae9dd3989c2ecae89b4dad5306f6cca3fee75e8b |
| s4-grid-main | dd33f14bed6d2177ec3bd3033318f8105d6560ffc305cc5ecb0a1360e5d8af4b | 2bb60444b983e0b33811bd09d1dc5e731220fda82c313376a43e7f5d251e992f |
| s4-semantic-tokens | 0a409d3fbe7f395d73cd6053c5997ed0af1305f11811f3e319d3f4d2f8b6d78c | 896b281e0a6f218648b497655a1702c5f109532cb38087b168e168c4a19a2cf6 |
| tab-overflow | fabd29f6f1d990621b856e098ebe1d4cb4d042962615daa1d5a5ceb4dc177f5f | adde66af41ef8fa657a7eed466e3be0da60d58683a7b514710ce1e047e9858af |

本轮无新增设计决策事项；R5 留待 FE2b。截图与测试证据交复审会话核对。

## 10. 04 阶段退出取证

### 源码传输与运行前核对

- 源码从 `/home/dev/gdds-fe` 的 `fe-vnext` 生成完整历史 bundle，文件为 `/home/dev/gdds-fe-logs/fe2a/exit-04/src-fe-vnext-c1b8fc81.bundle`，SHA256 `f6222aa9835989c6d4c1c0b86b6f99bb5eb573aaf1f34a0d4a24cf64fc41625f`。传至 CT04 `/home/dev/gdds-test-tmp/src-fe-vnext-c1b8fc81.bundle` 后，在共享仓库 `/home/dev/gateway-data-management-system` 验证并 fetch；`FETCH_HEAD` 为 `c1b8fc818a129c7b367234132621d91138fe6468`，且包含代码候选 `a80a2e93af663cda6f4f972a0840df5142df4cea`。CT04 `main` 起止均为 `c18b9b0993ef09f21f21e44b3f143156999b6bdf`。
- 传输与 worktree 操作记录：

  ```bash
  git -C /home/dev/gdds-fe bundle create \
    /home/dev/gdds-fe-logs/fe2a/exit-04/src-fe-vnext-c1b8fc81.bundle \
    refs/heads/fe-vnext
  sha256sum /home/dev/gdds-fe-logs/fe2a/exit-04/src-fe-vnext-c1b8fc81.bundle
  scp /home/dev/gdds-fe-logs/fe2a/exit-04/src-fe-vnext-c1b8fc81.bundle \
    ct108-gw-dms-04:/home/dev/gdds-test-tmp/src-fe-vnext-c1b8fc81.bundle
  git -C /home/dev/gateway-data-management-system bundle verify \
    /home/dev/gdds-test-tmp/src-fe-vnext-c1b8fc81.bundle
  git -C /home/dev/gateway-data-management-system fetch \
    /home/dev/gdds-test-tmp/src-fe-vnext-c1b8fc81.bundle refs/heads/fe-vnext
  git -C /home/dev/gateway-data-management-system worktree add --detach \
    /home/dev/gdds-fe-fe2a-a80a2e93af-04 a80a2e93af663cda6f4f972a0840df5142df4cea
  ln -s /home/dev/gateway-data-management-system/legacy \
    /home/dev/gdds-fe-fe2a-a80a2e93af-04/legacy
  ```

- 测试 worktree 为 `/home/dev/gdds-fe-fe2a-a80a2e93af-04`，新建 detached worktree，带 `legacy` 符号链接。runner 前后均 clean；没有复用现有 worktree。测量用途占用标记不存在。
- npm cache 使用 CT201 的 FE0 预填充，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`。CT04 默认目录 `/home/dev/gdds-fe-cache/frontend/npm-cache`，来源归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；04 预填充时间为 2026-11-02 10:29:01–10:29:22 UTC。本次未设置 `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`，未使用节点重新打包副本。
- Playwright 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`：config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；7 个 RootFS DiffID 为：
  1. `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  2. `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  3. `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`
- 前置记录：`/home/dev/gdds-fe-logs/fe2a/exit-04/preflight-04.log`，SHA256 `ad26c6851f57e69b8af5935caeaa42f8d60fb9146e40ce6827a5c9aaea273cf5`。

### CT04 完整 runner

- 节点 `gw-dms-test-04.lan`；worktree `/home/dev/gdds-fe-fe2a-a80a2e93af-04`。执行命令：`./frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2a/a80a2e93af-04`。
- runner 起止时间：2026-11-03T09:20:14Z–2026-11-03T09:20:39Z；起止 HEAD 均为 `a80a2e93af663cda6f4f972a0840df5142df4cea`；起止 frontend tree 均为 `f1c238248acc72b8be33fd50bb893e7539ff4caa`；exit code 0。17 个 Vitest 文件、72 项单测通过；4 个 Playwright e2e 通过；typecheck、lint、production build 和 production dist 检查通过。
- runner 日志 `/home/dev/gdds-fe-logs/fe2a/exit-04/frontend-tests-20261103T092014Z.log`，SHA256 `1fd6443994825992aace3e729eee424ab03cd557cab1e0fa6d8c87fc009ab105`。
- 外层 wrapper 起止时间：2026-11-03T09:19:51Z–2026-11-03T09:20:39Z。日志 `/home/dev/gdds-fe-logs/fe2a/exit-04/runner-wrapper-04.log`，SHA256 `16f3846ccedf1f2d23f0a6a7d5110f7c47cc67f9d0ce9a7005afd0bb49c08dbe`。日志记录的起止 HEAD/tree 与 runner 一致，exit code 0。
- 运行后 worktree 仍 clean，HEAD 与 frontend tree 未变化。

### CT04 截图

30 张截图位于 worktree 外目录 `/home/dev/gdds-fe-evidence/fe2a/a80a2e93af-04`，覆盖 1280 与 1920 两种宽度：

| 状态 | 文件名（1280 / 1920） | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- | --- |
| bundle-error | `bundle-error-1280.png` / `bundle-error-1920.png` | `b21a4a2240bf2719c462e002116cb5e81da72d4e618ed50c398123b63a6a34a7` | `f9589c5ca9a738662c7b13700177e7dbf9b3f0a8d815beeabe65867600f4ba3e` |
| dataset-replacement-browse | `dataset-replacement-browse-1280.png` / `dataset-replacement-browse-1920.png` | `fe14edb359aa77086b75a6d1e7fd3be64a83ceda81ba8c6f5dc43ce6ce513eec` | `974fd1e2aae8782dc837217e3471b4e88c2c6fd4ba0aea178157b40e747520c7` |
| formula-history | `formula-history-1280.png` / `formula-history-1920.png` | `47b892650a54d8ee47b3366dd551e5b58daec7b73bfde5a840bd84882add3cb5` | `831532993e2c7a9fad8ffb0c8728be7221ca6231bb5502958bac6b053b865318` |
| formula-preview | `formula-preview-1280.png` / `formula-preview-1920.png` | `d6aa19d3a5a1df731d3d25a93db8886ac79ccb2c90f2eef6ef46690cf087efb4` | `266f59b66390ca31a4db7fd7f5d414b2d5d7b7b463153753f440bf754d525018` |
| loading-skeleton | `loading-skeleton-1280.png` / `loading-skeleton-1920.png` | `4ff0390c8d74470c46102d4703ac698d16594c8b699ca38ef352dfa41565b603` | `3bbfa585429f136ae8864109f4aafc8529e115611623290091b7ea62c61f7fde` |
| navigation-fallback | `navigation-fallback-1280.png` / `navigation-fallback-1920.png` | `c3b1fec89fd5b4a28e5ab2b7a3a94d51821a99a0c614496308050e8559b5d418` | `b28dcd7e18679ed185aed9a82813ddda1e9707d886143d64b85bda3d7febd17c` |
| s3-header-history | `s3-header-history-1280.png` / `s3-header-history-1920.png` | `76a2bf4f77191aa8cd427b960dd58fe1ab7d7eef19295150f7bb953e2f11ce3e` | `a235950cd378d78cd2ecfa69587ccd3d87b67d35aa6372ad4e6c7fde5cd84802` |
| s3-header-review | `s3-header-review-1280.png` / `s3-header-review-1920.png` | `2ce4bccabf5b238d3a92eab14967a5c2b8651facfdb379dc5fd9034e2cf0b045` | `e6633ca1e2bd52f579e59e871b5c36a5b3e1bf9dfe7c12d5a89933020dad1309` |
| s3-header-upload | `s3-header-upload-1280.png` / `s3-header-upload-1920.png` | `18537557e768e5ac5d5fbc534eab791817f37916fb7c5a3d1c541a74e8c5e519` | `482ba0237a0312f363669fb505812077d3e4fa3513e4037cdca64f405e04fa66` |
| s3-workbench-upload | `s3-workbench-upload-1280.png` / `s3-workbench-upload-1920.png` | `5e5f68fbf68138da68e35192dee76be216ab6c85d693e27a372aeef4b31c0e6b` | `b639723b2f7f767988de0c0a86bf52381223acfc49f15a200eacc9433245b0b1` |
| s4-grid-debug | `s4-grid-debug-1280.png` / `s4-grid-debug-1920.png` | `d8750bb38d6945571e2ce69b24fb656e3f30409e2ec48708456060f4437ca161` | `2130a48593f6720983d1f4fe1aebc8e1107451ab6a7025a5563dfb1c4d103d42` |
| s4-grid-hover | `s4-grid-hover-1280.png` / `s4-grid-hover-1920.png` | `fdca73df8306966bcf43d05b78fc8c2a1ebc068ce35e0b3297eebdd1f391ba67` | `a27bf6e83c0337b2d78d4343ae9dd3989c2ecae89b4dad5306f6cca3fee75e8b` |
| s4-grid-main | `s4-grid-main-1280.png` / `s4-grid-main-1920.png` | `dd33f14bed6d2177ec3bd3033318f8105d6560ffc305cc5ecb0a1360e5d8af4b` | `2bb60444b983e0b33811bd09d1dc5e731220fda82c313376a43e7f5d251e992f` |
| s4-semantic-tokens | `s4-semantic-tokens-1280.png` / `s4-semantic-tokens-1920.png` | `0a409d3fbe7f395d73cd6053c5997ed0af1305f11811f3e319d3f4d2f8b6d78c` | `896b281e0a6f218648b497655a1702c5f109532cb38087b168e168c4a19a2cf6` |
| tab-overflow | `tab-overflow-1280.png` / `tab-overflow-1920.png` | `fabd29f6f1d990621b856e098ebe1d4cb4d042962615daa1d5a5ceb4dc177f5f` | `adde66af41ef8fa657a7eed466e3be0da60d58683a7b514710ce1e047e9858af` |
