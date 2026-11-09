# FE3b 04 取证核对 1：勘误复核

- 对象：勘误提交 `ed5d2c24e9`（`fe-vnext`，父提交 `a300b16485`），复核范围 `a300b16485..ed5d2c24e9`，
  只改 `docs/frontend-vnext/fe3b-evidence-04.md`。
- 依据：`fe3b-evidence-check-1.md` 中的 E1 与 P1。
- 核对者：审核会话（不是实施会话）。只读复核：比对文档 diff，在开发主机运行勘误所附脚本；另用核对 1 时
  我自己从 04 收集的来源做独立比对。没有在节点上运行任何东西。时间约 2026-11-09T05:40Z 至 05:45Z。

## 结论

**通过。** E1 的 5 个值已全部更正，§6 改成了能发现这类错误的脚本核对，其余内容没有变。证据核对 1 至此
完成，`ed5d2c24e9` 可以作为 FE3b 04 取证的 handoff。P1 尚未解决，仍待 owner 协调，见 §3。

## 1. 逐项

| 项目 | 结果 |
| --- | --- |
| 5 个值（第 99、151、194、215、219 行） | 与核对 1 表中的值逐字一致：p2r1 config `…ad9ec9`、`tracked_frontend_archive_sha256` `…4ec5292`、`missing-dbcfg` `…3585518b1`、Compose 日志 `…72b19b6…`、`suite-summary.txt` `…82866b5…` |
| bundle SHA | §1、§5 已注明“删除前两地一致，现已无法复核”，脚本按值列为唯一例外 |
| 其他改动 | diff 中只有上述 5 行、两处 bundle 注记、重写的 §6 和勘误说明，运行记录没有改动 |
| §6 脚本 | 文中脚本全文与 `/tmp/fe3b-evidence-verify/verify-fe3b-evidence.py`（SHA256 `3353af61…96cc`）逐字一致；判定规则符合要求（64 位必须在来源中，40 位必须是 git 对象，7–12 位为缩写或数字，其他长度报错） |

## 2. 复跑与独立比对

- **复跑：** 用勘误所附脚本和它的 16 个来源文件检查 `ed5d2c24e9` 的文档，输出与 §6 完全相同：
  197 个十六进制串，`index_mismatch: 0`，`failures: 0`，exit 0。
- **反例：** 同一脚本检查勘误前的 `a300b16485` 文档，能报出 E1 的全部 5 处错误：4 处“bad length”
  （63、63、57、63 位），1 处 Compose 日志“hex64 not in sources”。
  - 在我的临时目录中运行时，40 位值与缩写也报失败，因为那个目录是没有对象的空仓库，不是文档的问题。
- **来源一致性：** 勘误所用的 6 份日志与我在核对 1 中从 04 复制的日志逐字节相同。它的 `*.sha256` 来源文件中
  列出的 51 个文件哈希，全部与我在 04 上重算的结果一致。p2r1 manifest 的 `Config` 是 `…ad9ec9`。
- **独立比对：** 文中 132 个 64 位值里，122 个直接出现在我自己从 04 收集的来源中。其余 10 个是：
  - bundle SHA（豁免）；
  - 勘误会话 9 个 scratch 来源文件自身的 SHA256。脚本按 `source-index.txt` 重算这些文件并逐个比对，均一致。

## 3. 仍待处理

- **P1：** 开发主机主工作区 `/home/dev/gateway-data-management-system` 仍停在 `fe3b-evidence-04`
  （`a300b16485`）。`main` 仍检出在 `/home/dev/gdds-s5-design-main`，属于另一会话的 worktree。
  - 勘误按要求在 `/home/dev/gdds-fe` 的 `fe-vnext` 上完成：先快进到 `a300b16485`，再提交
    `ed5d2c24e9`，没有动主工作区。
  - 主工作区切回 `main` 后，`fe3b-evidence-04` 分支已经多余（其提交已在 `fe-vnext` 中），可以删除。由 owner 协调。
- 本报告与核对 1 一样，提交在本地分支 `fe3b-evidence-check-1` 上（worktree `/home/dev/gdds-fe3b-evcheck-report`），
  待 `main` 可用时合入，不推送。
- 开发主机 `/tmp/fe3b-evidence-verify/`（脚本与来源集合）可以删除，也可以保留到 FE3b 退出，由实施会话在退出清理时一并处理。

## 4. 下一步

1. owner 看图：确认 N3、N4、N7（见核对 1 §4、§5）。
2. 看图完成后，审核会话给出 FE3b 退出建议：tag 对象（建议指向 handoff `ed5d2c24e9`，被测代码为 `dac69890a8`）、
   合入方式、P1 处理与清理清单。
