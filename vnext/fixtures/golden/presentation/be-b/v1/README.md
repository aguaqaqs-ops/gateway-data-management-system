# BE-b presentation golden v1

五类向量来自 generator commit `f663fba2f5a58a9310d0c41803b797c2d00a835b`，17 个真实 Preview/History/replacement 场景。每文件 SHA、输入 manifest SHA、source vnext tree、实际 bundle/Submit outcome 在 manifest.json；全部 payload 原样保存，没有重新编号、手写导航或诊断。

`surface/` 包含真实 preimage、digest 与物理改写相等证明；`row-location/` 包含原五列 Parquet 的 base64/schema/解码行。`bundle/` 记录完整 manifest 与原 artifact closure；完整可直接交前端的成员树在对应外部生成原件，不把 golden JSON 当可下载 bundle。

专用节点 05，clean detached `/home/dev/gdds-be-b-b4`；两次生成逐字节相同。原输出 `/home/dev/gdds-test-tmp/be-b-fixtures-f663fba2f5-{a,b}`；交接副本与原始日志见 `/home/dev/gdds-stage-exchange/be-b/`。复验命令、固定输入、前端整体替换和剩余 B5 身份/OpenAPI/门禁绑定见 [前端交付](../../../../../../docs/backend-vnext/refactoring/formal/plans/be-b-frontend-delivery.md)。

`tests/test_presentation_golden.py` 验证五类消费者向量的 SHA/JCS、导航/诊断 Contract、surface preimage、typed locator schema/index，以及实际 bundle/closure 摘要闭合。生成器两次全输出比较另在节点原日志记录；不以 golden 自检替代生产生成或 B5 门禁。
