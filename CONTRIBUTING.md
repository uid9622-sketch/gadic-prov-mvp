# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-文档-创建-gadic-contributing-20261114

# CONTRIBUTING · 参与贡献指南

欢迎参与本项目！这里说清楚：怎么报问题、怎么提代码、什么会被接受、什么不会被接受。

## 一、分支模型

| 分支 | 用途 | 规则 |
| --- | --- | --- |
| `main` | 唯一稳定分支 | 受保护：只接受 PR 合入，不接受直接推送 |
| `feat/<名称>` | 新功能 | 例：`feat/tsa-integration` |
| `fix/<名称>` | 修 bug | 例：`fix/verify-edge-case` |
| `docs/<名称>` | 文档改进 | 例：`docs/spec-typo` |
| `test/<名称>` | 补测试 | 例：`test/merkle-fuzz` |

**贡献流程**：Fork 本仓 → 从 `main` 拉出上述命名分支 → 改动 → 本地全绿 → 发 Pull Request → CI 自动验证 → 维护者评审 → 合入。

## 二、提交前必须过的三道闸（CI 会替你重跑一遍）

1. **测试全绿**：`python -m pytest tests/ -q`（当前基线 22 个用例）
2. **完整性自校验**：`sha256sum -c SHA256SUMS.sha256`（清单内文件哈希必须对得上）
3. **端到端验证**：
   ```bash
   PYTHONPATH=src python3 -m gprov.cli.cli verify \
     ./examples/synthetic/work-001.txt ./evidence/record-001 \
     --trust-policy ./config/trust-policy.json
   ```
   预期 `VERIFIED_WITH_LIMITATIONS`（退出码 0）。

## 三、提交（commit）要求

- **必须**：`git commit -s`（Signed-off-by，DCO 声明你有权提交这份代码）
- **建议**：开启 GPG/SSH 签名（`git config commit.gpgsign true`），通过后提交旁会显示 Verified
- 每个文件可携带一行溯源标记（形如 `# 🧬 #龍芯⚡️...`）；**已有的溯源标记请勿删除**——它们是文件出身证明，删了 CI 会退回你的 PR

## 四、什么会被接受 / 拒绝

**接受**：修 bug、补测试、文档纠错、兼容性改进、性能优化（附基准数据）。

**拒绝（无需讨论）**：
- 含真实密钥、令牌、个人身份信息的任何提交
- 删除或篡改溯源标记、证据文件、哈希清单的提交
- 改动验证逻辑但不同步更新证据链的提交
- 违反 `LICENSE-NOTICE.md` 第三节（思想条款）的衍生提交

## 五、核心算法改动走特殊通道

`src/gprov/time_ganzhi.py`（干支纪时桥）、`canonicalization/`（规范化算法）、`transparency/merkle.py`（Merkle 审证）属于核心算法资产（见 `docs/IP-REGISTRY.md`）。改动这些文件的 PR 需要：
1. 在 PR 描述里说明数学依据
2. 附上新旧行为的对照测试
3. 接受更长的评审周期

## 六、报告安全问题时

**请勿公开提交含漏洞细节的 Issue**。通过 Issue 留言"请私联"或联系仓库所有者，收到后会登记响应。
