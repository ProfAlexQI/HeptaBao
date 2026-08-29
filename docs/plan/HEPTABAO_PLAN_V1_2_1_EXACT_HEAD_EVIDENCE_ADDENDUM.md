# HeptaBao Plan V1.2.1 Exact-Head Evidence Addendum

**Plan ID：** `HEPTABAO-PLAN-2026-08-28`  
**Revision：** `1.2.1`  
**状态：** `NORMATIVE_OPERATIONAL_ADDENDUM / REMEDIATION_IMPLEMENTED / NOT_QUALIFIED / AUTHORITY_EFFECT_NONE`  
**继承：** `HEPTABAO_MASTER_DEVELOPMENT_PLAN_V1_2` 与 `HEPTABAO_PLAN_V1_2_1_EXECUTION_DEEPENING`  
**主题：** 完整 H02 exact-head matrix、应用级结果验证、失败保全与 authority re-evaluation

## 1. 触发原因

对 V1.2.1 exact head 的再审计发现，原 `plan-integrity-v4` 在一个 shell loop 中依次运行多个 OpenRaft probe，并使用 shell fail-fast。该结构存在两个独立缺陷：

1. 第一个非零退出可能停止后续 entry，导致 2 toolchains × 3 seeds × 4 probe kinds 的完整集合没有被执行和保全；
2. hostile-snapshot parent 对 `EXECUTED_FAIL` 没有返回非零，而聚合 workflow 没有解析其 application JSON，因此 guarded state 发生变化时可能出现“应用失败、CI 成功”的错误结果。

这不是 authority 或 qualification 缺口的重新定义，而是 repository-controlled evidence production 缺口。它纳入 `HB-BLK-REPO-008`、`011` 与 `013` 的 closure criteria，所有 blocker 仍保持 `REMEDIATION_IMPLEMENTED`，直到 exact-head runner、required review 和 closure receipt 完整。

## 2. 本修订交付

### 2.1 统一执行器

`scripts/h02_exact_head_matrix_v1.py`：

- 固定执行 24 个 entry；
- 不因前一 entry 失败而中止；
- 使用 argv 数组而不是 shell command 拼接；
- 每个 entry 记录 stdout、stderr、exit、duration 和 digest；
- 对 in-memory、hostile、blocker、durable 四类输出分别做应用级验证；
- 输出 schema-valid `matrix-summary.json`；
- 只有 24/24 application PASS 且 process exit 0 时返回成功。

### 2.2 Hostile-snapshot 退出语义

`openraft_fault_lab` 的 parent result 使用明确映射：

```text
EXECUTED_PASS → 0
EXECUTED_FAIL → 1
BLOCKED       → 2
unknown       → 3
```

Rust negative tests保证安全失败不能返回 0。统一执行器仍独立解析 JSON，不信任 process exit 作为唯一结论。

### 2.3 Machine summary schema

`heptabao.h02-exact-head-matrix-summary.v1` 固定：

- repository/ref/commit/tree/clean-tree；
- manifest 与 lock digest；
- toolchain、seed 和 probe kind；
- 24 个唯一 entry；
- 每个 raw output/exit digest；
- pass/fail/blocked/unknown/unexecuted 计数；
- missing/unexpected entry；
- qualification、compatibility、selection 和 authority 常量。

`result=PASS` 只有在 `pass=24` 且其他计数为 0 时 schema 才允许。

### 2.4 Workflow ordering

`plan-integrity-v4` 调整为：

```text
exact checkout
→ Python V1.2/V1.2.1 validation
→ locked metadata
→ fmt/test/clippy on Rust 1.88 and 1.98
→ capture all 24 entries without early abort
→ upload every raw diagnostic
→ independent final summary/digest gate
→ authority re-evaluation sentinel
```

OpenRaft job显式安装自己的 Python validation dependencies，不再错误依赖另一 job 的隔离环境。

## 3. Closure 规则深化

技术结果分成三层：

1. **Process result**：是否启动、timeout、exit code；
2. **Application result**：JSON/JSONL schema、status、case 与安全不变量；
3. **Aggregate result**：required entry 集合、计数、digest 与 source binding 是否完整。

三层必须同时通过。任何一层失败都不得被后续绿灯覆盖。原始失败仍保留并进入 supersession graph。

## 4. 当前 blocker 状态

### Repository-controlled

所有 repository blocker 仍为 `REMEDIATION_IMPLEMENTED`。本修订不自行写入 `EXACT_HEAD_EXECUTED` 或 `CLOSED`，因为：

- 新 exact head 尚需获得 runner；
- 全部 required jobs 尚需产生 current PASS；
- critical blocker 尚需真实独立 reviewer；
- closure receipt 尚需签名、freshness 和 revocation verification。

### External

以下状态不受本修订改变并继续 `EXTERNAL_ACTION_REQUIRED`：

- GitHub ruleset 与 negative control；
- 独立 reviewer identities；
- legal/clean-room/outbound license；
- private disclosure、24×7 roster 与 incident drill；
- isolated signer、trust root、transparency、revocation；
- restricted Oracle 与 signed sanitized transfer；
- separately operated kernel/VM power-cut lab；
- independent operator/credential-root reproduction。

## 5. Exact-head execution acceptance

本修订的 repository-controlled execution candidate 至少要求：

```text
plan-and-python = PASS
root-rust = PASS
openraft exact metadata = PASS
Rust 1.88 fmt/test/clippy = PASS
Rust 1.98 fmt/test/clippy = PASS
24/24 matrix entries = PASS
raw artifact upload = PASS
summary schema and digest re-verification = PASS
authority sentinel = PASS
```

queued、pending、skipped、cancelled、empty steps 或未分配 runner 都是 `UNEXECUTED`，不是 PASS。

## 6. 后续执行顺序

1. 在独立 child branch/PR 上完成本修订；
2. 触发 V1.2、V1.2.1 与 H02 exact-head gates；
3. 分类每一个 executable failure，不选择性删除结果；
4. 修复后在新 SHA 完整重跑；
5. 生成 unsigned technical closure candidate；
6. 请求 program/security/storage-platform independent review；
7. 签发 current、scoped、unrevoked blocker closure receipts；
8. 外部 action packages 按各自完成对象继续闭环。

只有前 7 步全部满足，repository-controlled critical blocker 才能进入 `CLOSED`。外部 blocker 不能被这些步骤关闭。

## 7. Authority boundary

本 addendum、代码、测试、CI 和 technical summary 均不能：

- 选择 OpenRaft；
- 证明 kernel power-cut durability；
- 形成 H02 qualification；
- 创建 compatibility claim；
- 授予 production、migration、release 或 mixed-cluster authority。

固定状态：

```text
qualification=false
compatibility_claim=false
selected_candidates=[]
selection_effect=NONE
authority_effect=NONE
```
