# gadic-prov-mvp

![CI](https://img.shields.io/github/actions/workflow/status/uid9622-sketch/gadic-prov-mvp/ci.yml?branch=main\&label=CI)
![Code License](https://img.shields.io/badge/code-MulanPSL--2.0-blue)
![Docs License](https://img.shields.io/badge/docs-CC_BY--NC--SA_4.0-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)
![Tests](https://img.shields.io/badge/tests-22%20passing-brightgreen)
![Provenance](https://img.shields.io/badge/provenance-DNA%20stamped%20%2B%20SHA--256-9cf)


GADIC-PROV-MVP-001 · 全球可信创作与数据溯源原型 · 本地 MVP 实现（v0.2.0）

规范原文（冻结版）：`specs/GADIC-PROV-MVP-001-v0.2.0-frozen.md`（以其 SHA-256 为准）

## 五模块实现状态

| 模块 | 状态 | 证据 |
| --- | --- | --- |
| M1 创作登记 | PASS（本地合成样本） | `tests/test_matrix.py` + 运行报告 |
| M2 Ed25519 签名 | PASS（本地合成样本） | T-003/004/005 |
| M3 RFC 3161 | NOT_CONFIGURED | 未配置真实 TSA；未配置时如实降级（T-008） |
| M4 透明日志 | PASS（本地篡改检测） | T-012~T-017；本地日志 ≠ 独立第三方见证 |
| M5 独立验证器 | PASS（干净输入重放） | T-018/T-019 |

## 快速开始

```bash
cd gadic-prov-mvp
PYTHONPATH=src python3 -m gprov.cli.cli keys --key-name gadic-author
PYTHONPATH=src python3 -m gprov.cli.cli keys --key-name gadic-log
PYTHONPATH=src python3 -m gprov.cli.cli register ./examples/synthetic/work-001.txt --out ./evidence/record-001
PYTHONPATH=src python3 -m gprov.cli.cli sign ./evidence/record-001/manifest.json --record-dir ./evidence/record-001
PYTHONPATH=src python3 -m gprov.cli.cli log append --record-dir ./evidence/record-001
PYTHONPATH=src python3 -m gprov.cli.cli verify ./examples/synthetic/work-001.txt ./evidence/record-001 --trust-policy ./config/trust-policy.json --format json
pytest tests/
```

## 安全红线（与规范 §0.3 一致）

- 未配置 TSA → `NOT_CONFIGURED`，不生成假令牌。
- 本地日志只做本地篡改检测；多方见证需独立运营主体（Phase 5）。
- 证据包内公钥不自动可信，必须匹配 Trust Policy 指纹。
- 私钥只存 `keys/`（0600），绝不进入 Notion / 仓库 / 报告。

<!-- 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-文档-创建-b3356305 -->

## 许可

代码：MulanPSL-2.0 ｜ 文档与规范：CC BY-NC-SA 4.0 ｜ 思想与方法论保护条款见 `LICENSE-NOTICE.md`

## 参与

欢迎贡献！规则见 [CONTRIBUTING.md](CONTRIBUTING.md)（分支模型 / 三道闸 / 提交要求 / 核心算法特殊通道）。
发布前清单见 [docs/RELEASE-CHECKLIST.md](docs/RELEASE-CHECKLIST.md)；
核心算法与思想资产登记见 [docs/IP-REGISTRY.md](docs/IP-REGISTRY.md)。
