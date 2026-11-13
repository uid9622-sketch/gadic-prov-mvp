# GADIC-PROV-MVP-001 运行报告（Phase 1 本地最小证据链）

> 包青天裁定：本报告只声明**本地合成样本运行结果**。所有 PASS 均限"本地测试环境"，不代表真实 TSA / 独立见证 / 法律作者身份证明（§0.2/§0.3）。

## 按 §13.1 模板

```
Project: GADIC-PROV-MVP-001
Build/Commit: 本地未提交（无 git 仓）
Verifier Version: gprov-verify 0.2.0
OS / Runtime: macOS (Darwin) / Python 3.12.15 / cryptography 50.0.0 / pytest 9.1.1
Dependency Lock Hash: 未锁定（pip freeze 未归档）→ 列入待办
Test Date (RFC3339): 2026-11-14T05:10+08:00（本机时间·SELF_ASSERTED）
Test Command: python3 -m pytest tests/ -q ; python3 scripts/demo_e2e.py
Total: 22
Passed: 22
Failed: 0
Skipped: 0
Not Run: T-009/010/011/021/024（依赖真实 TSA 或撤销流程，NOT_CONFIGURED）
External Services: 无（全离线；TSA 未配置）
Raw Output Path: reports/ + tests/ 输出
Evidence Bundle Hash: 见 reports/hashes-2026-11-14.json
Known Limitations: 见下节
Reviewer: 上帝之眼（测试矩阵）→ 包青天（状态裁定）
Review Status: 本地 PASS（受控试用前须补 §13.2 全部门槛）
```

## 测试矩阵结果

| ID | 结果 | 说明 |
| --- | --- | --- |
| T-001 | PASS | 同文件重复摘要一致 |
| T-002 | PASS | 单字节改动 → 摘要不同 |
| T-003 | PASS | 正确公钥验签通过 |
| T-004 | PASS | 错误公钥验签失败 |
| T-005 | PASS | 签名后改 Manifest → FAIL |
| T-006 | PASS | 字段顺序不同 → JCS 字节一致 |
| T-007 | PASS | 重复 JSON 键 → 拒绝（DuplicateKeyError） |
| T-008 | PASS | 未配置 TSA → NOT_CONFIGURED，零假令牌 |
| T-009~011, 024 | NOT_RUN | 依赖真实 TSA 配置 |
| T-012 | PASS | 追加 5 事件，逐前缀根可复算 |
| T-013 | PASS | 改叶子 → inclusion 失败 |
| T-014 | PASS | 篡改路径 → FAIL |
| T-015 | PASS | m×n 全对（12 层树，66 对）+ 篡改/冗余节点拒绝 |
| T-016 | PASS | 同 tree_size 冲突根 → ForkDetected |
| T-017 | PASS | 截断尾部 → 与检查点比对发现根不匹配 |
| T-018 | PASS | 无时间戳 → VERIFIED_WITH_LIMITATIONS，绝不 VERIFIED |
| T-019 | PASS | 验证器纯磁盘材料+带外策略重放 |
| T-020 | PASS | 证据包/日志零私钥材料 |
| T-021 | NOT_RUN | 撤销流程属 Phase 4 |
| T-022 | PASS | 路径越界 → BundleError 拒绝 |
| T-025 | PASS | 伪造检查点密钥 → 验签失败（端到端运行中真实拦截过一次） |

## 端到端运行（合成样本）

- record_id: `urn:uuid:4c2a7566-7839-4094-8909-a7bebd4285a3`
- asset_hash: `ea836c8bb14e51f0abae1036509922748e7feb3950b640a9cf22f2bda1f74668`
- envelope SHA-256（= TSA imprint 对象）: `2d2d7c44a50806f16790b26baf70f8165c07114ea197e62c834ac9301599a12d`
- 独立验证: `VERIFIED_WITH_LIMITATIONS`（exit 0；timestamp=NOT_CONFIGURED）

## 哈希账本（权威值以 reports/hashes-2026-11-14.json 为准）

| 对象 | SHA-256 |
| --- | --- |
| 冻结规范 specs/GADIC-PROV-MVP-001-v0.2.0-frozen.md | `ae61f37630a05bd79cf056f96fcc98509b5cce3cdfcdf95182fd146c4f858a17` |
| record-001 manifest.json | `ef16cb6f5159ca80042436d8fa58e2b60defa03a1d4df6bb9940ca635c80fd6f` |
| signature-envelope.json | `2d2d7c44a50806f16790b26baf70f8165c07114ea197e62c834ac9301599a12d` |
| verification-report.json | `65b10ad6723660f0158ca5f42bdf74f2763890321307f71154cd0083643b8d4d` |
| transparency-log events.jsonl | `85eea5c15216cd43568165e1c52148bff8e2ab06f05de1176c0e90a8621a28a4` |
| transparency-log checkpoints.jsonl | `88bafb6155021256b95b832e3a56f50d3cb64667a15ea4b1b17a87e1540ec065` |
| 合成作品 asset（work-001.txt） | `ea836c8bb14e51f0abae1036509922748e7feb3950b640a9cf22f2bda1f74668` |

冻结规范 SHA-1 `92daf2e0fe1e1ec9eb755d4f20a24639a2fc54dc` · MD5 `b96e5a8035db47a68a01262d87018843` · 41,057 字节。

> 注：Notion 页 §16 记载的回填前摘要为 `52ef32…aa78b`（41,194 字节）。本地冻结文件与其字节不同（编辑差异），按规范"回填说明"规则处理：本地冻结文件为权威对象，其哈希如上；Notion 回填后如再导出须另算新摘要并记为 v0.2.0-hashfix。

## Known Limitations

1. **M3 = NOT_CONFIGURED**：未接真实 TSA；`timestamp` 命令只支持 openssl 子进程路径，未实测。
2. **本地日志 ≠ 独立见证**：M4 的 PASS 仅为本地篡改检测能力（§11.3）。
3. **一致性证明验证算法**采用"生成对称重放"（等价 RFC 6962 §2.1.2），已由 T-015 全对+篡改交叉验证；正式发布前应补官方测试向量。
4. **JCS 浮点/UTF-16 键序边界**未实现（本项目字段不含浮点；键名 ASCII），已在模块 docstring 声明。
5. **依赖未锁**（pip freeze 未归档）；撤销/轮换演练未做（T-021）。
6. 演示密钥为合成密钥，**不得**用于真实签发（§16 签章安全说明）。

## 结论

Phase 1（本地最小证据链）五模块中 M1/M2/M4/M5 已可运行并通过本地测试矩阵；M3 如实 NOT_CONFIGURED。距 §13.2 验收门槛还差：真实 TSA、依赖锁定、官方测试向量、撤销演练、外部见证。

---

## 追加记录（2026-11-14 第二轮·干支合并 + DNA 盖章 + 落库）

1. **干支纪时桥合并**（老大合并令）：新增 `src/gprov/time_ganzhi.py`，复用真身 `longhun-system/08_BIN/lh_time_engine.py`（年干支/月干支_精准/日干支/时辰），log-event 增加可选字段 `ganzhi_stamp`（加性变更，符合 §5.6）。诚实边界写死：干支戳由本机时钟推出 = SELF_ASSERTED 文化纪时辅助字段，**非可信时间**，不参与密码学绑定，不替代 RFC 3161。引擎缺席返回 None 不编造（与 §0.3 同款）。测试 +3（2026=丙午年基准互证/字段存在性/缺席回退），矩阵 19→22 全绿。
2. **DNA 盖章**：26 个文本文件逐文件独立 DNA（`#龍芯⚡️` 标记，真身 lh_dna_generator.py），符合全局永恒审计闸判据；`SHA256SUMS.sha256` 全量清单（`sha256sum -c` 可校验）。
3. **冻结规范 hashfix**：规范文件盖章后字节变化（41,057→41,147），按其 §16 回填说明规则记 **v0.2.0-hashfix**：
   - 新 SHA-256：`c153b21900930c1af998b5297ca8e57994cdef0c480b0989f44bf6c283ffbdee`
   - 旧值 `ae61f376…858a17`（41,057 字节，盖章前）留档于 Notion §18.2。
4. 端到端复跑：VERIFIED_WITH_LIMITATIONS（exit 0）· log 事件干支戳 `丙午年·己亥月·壬辰日·卯时`。
5. 本地 git 落库（DNA+SHA256 齐备后提交）；对外 push 未执行——外发面协议闸：需老大一句话定目标仓（gitee 私有/公开）。

<!-- 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-文档-创建-8ca74c7a -->
