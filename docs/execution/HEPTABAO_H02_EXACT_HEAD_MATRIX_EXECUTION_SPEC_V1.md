# HeptaBao H02 Exact-Head Matrix Execution Specification V1

**状态：** `NORMATIVE / IMPLEMENTATION_ACTIVE / NOT_QUALIFIED / AUTHORITY_EFFECT_NONE`  
**适用范围：** H02 OpenRaft candidate、in-memory cluster、hostile snapshot、OS/durable/clock closure 与 logical durable-store probe  
**执行器：** `scripts/h02_exact_head_matrix_v1.py`  
**机器摘要：** `schemas/heptabao_h02_exact_head_matrix_summary_v1.schema.json`  
**关联 blocker：** `HB-BLK-REPO-004`、`HB-BLK-REPO-006`–`011`、`HB-BLK-REPO-013`

## 1. 目的

本规范把 H02 exact-head 技术闭环从“若干 cargo 命令”提升为一个完整、不可选择性丢失、同时验证 transport 与 application semantics 的证据生产过程。它专门阻止下列错误成功：

- 第一个非零退出使 shell 提前终止，后续 toolchain、seed 或 probe 没有执行；
- 进程退出码为 0，但 JSON 明确报告 `EXECUTED_FAIL`、`FAIL` 或受保护状态发生变化；
- 输出不是合法 JSON/JSONL，却因为命令本身退出 0 被当成通过；
- 只验证 durable-store，而没有验证 in-memory、hostile-snapshot 和 blocker-closure 的应用结果；
- 只保留 stdout，丢失 stderr、exit code、失败 seed 或超时事实；
- 用一个聚合 GitHub job conclusion 代替 24 个必需 entry 的逐项结果；
- 在 source、tree、manifest 或 lock drift 后复用旧 summary；
- 技术矩阵通过后自动选择 OpenRaft 或授予任何 authority。

## 2. 固定矩阵

V1 的 required matrix 固定为：

```text
2 toolchains × 3 seeds × 4 probe kinds = 24 entries
```

### 2.1 Toolchains

- Rust `1.88.0`：当前 OpenRaft alpha.33 exact graph 的已声明 effective floor；
- Rust `1.98.0`：当前 HeptaBao development baseline。

Rust 1.85–1.87 的边界失败由单独 MSRV lane 记录，不得作为本矩阵的有效通过 entry，也不得通过替换为更高版本而隐藏。

### 2.2 Seeds

- `0x5eed20260828cafe`
- `0x8badf00d12345678`
- `0xd15ea5e5cafef00d`

任何 seed 失败都使整个 summary 为 `FAIL`。禁止只重跑成功 seed、删除失败 entry，或用不同 seed 替换失败 seed。

### 2.3 Probe kinds

| Kind | Binary | 应用级通过条件 |
|---|---|---|
| `inmemory` | `heptabao-h02-openraft-inmemory-cluster` | 一个 meta + 六个唯一 case；所有 case 为 `PASS`；测试内存边界与 authority 常量正确 |
| `hostile` | `heptabao-h02-openraft-fault-lab --mode hostile-snapshot-parent` | schema 精确；phase reached；status=`EXECUTED_PASS`；outcome=`REJECTED_OR_ABORTED_AFTER_INJECTION`；authority 常量正确 |
| `blocker` | `heptabao-h02-openraft-blocker-closure-lab --mode all` | 总状态与 OS suspend、durable faults、clock faults 三个 component 均为 `EXECUTED_PASS` |
| `durable` | `heptabao-h02-openraft-durable-store-lab` | 七个唯一 case 全部 `PASS`；persist-before-publish、atomic bundle、restart、ReadIndex、corruption rejection 均为 true；不得声称 kernel power loss 或 production selection |

## 3. 双重结果判定

每个 entry 的结论由三层同时决定：

1. **Process result**：进程是否启动、是否超时以及 exit code；
2. **Application result**：JSON/JSONL 中的 status、case 与安全不变量；
3. **Aggregate result**：24 个 required entry、source binding、计数和 artifact digest 是否闭合。

每个 entry 必须同时满足：

```text
process exit code == 0
AND
application-level semantic validator == EXECUTED_PASS
```

进程退出码只是 transport evidence，不是应用正确性证明。以下组合必须 fail closed：

| Exit | Application | 结论 |
|---:|---|---|
| 0 | `EXECUTED_PASS` 且全部结构/不变量满足 | `PASS` |
| 0 | `EXECUTED_FAIL` / case `FAIL` / guarded-state change | `FAIL` |
| 0 | JSON 无效、字段缺失、case 重复或 authority drift | `FAIL` |
| 非 0 | 输出声称通过 | `FAIL` |
| 非 0 | 输出明确 blocked | `BLOCKED` 或 `FAIL`，按执行阶段分类 |
| 无 exit | 进程未启动 | `UNEXECUTED` |
| timeout | 任意 | `FAIL`，除非另有签名的 infrastructure disposition |

Hostile-snapshot binary 自身也必须保证 `EXECUTED_FAIL` 返回非零；聚合执行器仍必须独立解析 JSON，形成 defense in depth。

## 4. 完整保留规则

无论前一 entry 是否失败，执行器都必须继续剩余 matrix。每个 entry 至少保留：

- entry ID、kind、binary；
- toolchain 与 seed；
- exact argv，不通过 shell 拼接；
- start/end UTC 与 duration；
- exit code 或不可用原因；
- timeout 标记；
- stdout 原文与 SHA-256；
- stderr 原文与 SHA-256；
- application status；
- semantic validation errors；
- final conclusion。

输出文件使用唯一 entry ID，禁止覆盖。失败输出和通过输出具有相同保留优先级。

## 5. Exact-source binding

执行前必须验证并传入：

```text
repository = ProfHepta/HeptaBao
ref
40-hex commit
40-hex tree
clean tree = true
manifest path + digest
committed Cargo.lock path + digest
```

Workflow 必须 checkout 显式 PR head SHA 或 push SHA，使用 `persist-credentials: false` 和 `contents: read`。运行期间不得修改 repository tracked files。summary 中的 source 与 dependency digest 不匹配时，结果无效并分类 `BASE_DRIFT` 或 `FAIL`。

## 6. Machine summary

执行器必须生成 `matrix-summary.json`，schema 为：

```text
heptabao.h02-exact-head-matrix-summary.v1
```

`result=PASS` 仅在以下全部成立时允许：

```text
required entries = 24
recorded entries = 24
executed entries = 24
pass = 24
fail = 0
blocked = 0
unknown = 0
unexecuted = 0
missing entry IDs = []
unexpected entry IDs = []
qualification = false
compatibility_claim = false
selection_effect = NONE
authority_effect = NONE
```

Schema-valid 只证明对象结构；workflow 的 final gate 还必须重新计算 entry ID 集合、计数、source/lock digest 与应用语义。summary 本身不是签名 closure receipt。

## 7. Workflow ordering

标准顺序：

```text
checkout exact SHA
→ verify clean source
→ install exact toolchains
→ cargo metadata --locked
→ V1.2/V1.2.1 semantic validators
→ fmt/test/clippy for both effective toolchains
→ execute all 24 entries without early abort
→ write summary and raw entry files
→ upload all diagnostics with if: always()
→ final fail-closed summary gate
→ authority sentinel
```

矩阵执行步骤可以返回内部非零，但 workflow 必须先完成 diagnostics upload，再由独立 final gate 失败。不得使用 `continue-on-error` 将失败 job 伪装成成功，也不得在 upload 前直接退出整个 job。

## 8. Retry、flake 与 supersession

- 同一 SHA rerun 保留原 run/attempt；
- runner 未分配、provider outage 等可以作为 infrastructure retry，但必须有 provider/job evidence；
- 已开始 cargo 或应用执行后的 compile/runtime/semantic failure 不得回标 infrastructure；
- 修复产生新 commit 后，旧 summary 进入 superseded graph；
- flake 必须固定 seed、找到 nondeterminism root cause、增加 deterministic control，并在同 exact head 完成规定重复验证；
- 任何 matrix、toolchain、seed、probe、validator 或 schema 变化都需要新 summary 与新 closure receipt。

## 9. 与 blocker closure receipt 的关系

Matrix summary 是 repository-controlled blocker closure receipt 的执行输入，不是最终 receipt。最终 `heptabao.blocker-closure-receipt.v1` 还必须绑定：

- normative manifest、blocker register、validator 与 dependency lock digest；
- workflow/run/attempt/job/runner identity；
- artifact provider ID 与 archive digest；
- criterion mapping；
- findings；
- required independent review；
- signature、expiry、revocation 和 supersession。

Critical blocker 不能由作者或 GitHub Actions 自行进入 `CLOSED`。

## 10. 非范围与 authority boundary

本规范不提供：

- kernel/VM power-cut 或 filesystem crash-consistency 独立实验室证据；
- per-node time namespace 或真实 kernel clock skew；
- 独立 operator/credential root/artifact custody 复现；
- OpenRaft prototype 或 production selection；
- H00/H01/H02 qualification；
- compatibility、production、migration、release 或 mixed-cluster authority。

所有 summary、workflow 与 receipt candidate 必须保持：

```text
qualification=false
compatibility_claim=false
selection_effect=NONE
authority_effect=NONE
```
