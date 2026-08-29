# HeptaBao Durability 与 Crash-Consistency Contract V1

## 1. 术语

- **accepted**：接口接收请求，不代表 durable；
- **persisted**：bytes 已提交到 profile 声明的持久层接口；
- **published**：新的 generation 成为唯一 current state；
- **committed**：满足 profile 的 quorum/transaction/fsync 条件且可在 crash 后恢复；
- **applied**：deterministic state machine 已应用 committed command；
- **acknowledged**：客户端或 callback 已收到成功。

必须满足 `committed HB acknowledged`。内存可见 candidate state 必须在 `published` 后更新。

## 2. 文件型 generation protocol

推荐布局：

```text
generations/<N>/log
                    /state
                    /snapshot
                    /membership
                    /manifest
CURRENT.tmp → fsync → atomic replace CURRENT → parent fsync
```

`manifest` 包含 format version、generation、component length/digest、previous generation、cluster ID、last log、applied index 和 membership epoch。恢复只接受 CURRENT 指向且所有 component 完整匹配的 generation；可回退到明确 previous generation，但不得静默初始化为空。

单一 bundle 文件可以替代多文件 generation，但同样必须 versioned、bounded、checksummed/authenticated、atomic replace 并 parent sync。

## 3. 原子写要求

1. 创建同目录唯一 temp file；
2. write-all，拒绝 partial success；
3. flush + file sync；
4. atomic replace；
5. parent directory sync（平台支持时）；
6. 重新读取 header/generation/digest 可选验证；
7. 更新内存 authoritative state；
8. 才能 callback/ack。

Windows/其他平台如不能证明 replace + directory durability，profile 必须明确降级为 `UNQUALIFIED`，并提供 crash recovery journal/manifest；不得把 no-op parent sync 写成跨平台证明。

## 4. 必测故障

- short/partial/torn write；
- lost/unordered fsync；
- disk full、quota、read-only、permission change；
- I/O delay/hang/cancel；
- temp/previous/current file crash points；
- corruption、truncation、bit flip、component swap；
- process kill、host reboot、VM power cut；
- snapshot build/install 与 concurrent apply；
- schema upgrade/downgrade interruption；
- clock rollback/forward 与 monotonic discontinuity；
- multi-process node restart 与 per-node directory isolation。

程序主动 sleep 或主动 truncate 只能叫 logical fault simulation，不能替代 kernel/filesystem power-cut evidence。

## 5. RPO/RTO

生产 committed-write 目标为 RPO=0。RTO 必须按 profile/规模测量。任何无法证明的 backend/platform 组合保持 unsupported。恢复过程不能调用外部 effect，也不能在 integrity failure 时默认为空数据库。

## 6. Raft 特定要求

vote、committed index、log append/truncate/purge、state apply、snapshot 与 membership 都有独立 crash point。`IOFlushed` 只能在所声明 durable point 后完成；state-machine responder 只能在 state generation durable publish 后发送。snapshot install 不允许 state/snapshot 交叉 generation。

## 7. Initialized-store lifecycle and rollback-safe replacement

A durable store has three explicit caller-selected operations:

1. `create-new` creates the first authoritative generation and only then publishes a
   versioned, domain-bound initialization marker;
2. `reopen-existing` requires both a valid marker and a valid authoritative generation;
3. `adopt-legacy` is an explicit migration operation that validates the complete legacy
   envelope, schema and invariants before publishing a marker.

The ordinary reopen path MUST NOT create directories, initialize defaults, adopt legacy
state, or infer that missing files mean a fresh store. Deleting both a marker and its
authoritative generation remains data loss; it does not become an implicit bootstrap
because the caller must still select `reopen-existing`.

Interrupted replacement recovery follows these rules:

- a missing current file plus exactly one `.previous` candidate may recover that candidate;
- multiple previous candidates are ambiguous and fail closed;
- a present current file is validated before any stale previous candidate is removed;
- a corrupt current file never falls back silently to a previous generation;
- one stale previous file may be retired only after current envelope, schema and domain
  invariants validate and the parent directory is synchronized where supported;
- orphan temporary files cannot authorize create-new or legacy adoption.

Tests MUST cover fresh create/reopen, missing generation, deleted directory, explicit
legacy adoption, corrupted marker, stale previous cleanup, corrupt-current no-rollback,
and multiple-previous ambiguity.

These repository-level guarantees do not establish storage-controller cache persistence,
kernel power-cut safety, or filesystem-specific crash consistency. Those require the
separately operated laboratory evidence defined by the external action package.
