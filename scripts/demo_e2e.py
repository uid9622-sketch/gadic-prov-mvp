"""GADIC-PROV-MVP-001 端到端合成样本演示（Phase 1 验收运行）。

产出：keys/ + evidence/record-001 + config/trust-policy.json
     + reports/verification-report.json + reports/run-report-2026-11-14.md
全部数据为合成样本，不含任何真实作品或真实权利声明。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gprov.canonicalization.canonical import jcs, strict_loads
from gprov.registration.hashing import sha256_bytes
from gprov.registration.register import register
from gprov.signing.signing import generate_keypair, sign_manifest, load_private
from gprov.transparency.transparency import TransparencyLog
from gprov.verification.verifier import verify_bundle

KEYS = os.path.join(ROOT, "keys")
EVID = os.path.join(ROOT, "evidence")
LOG_DIR = os.path.join(EVID, "transparency-log")
CONF = os.path.join(ROOT, "config")
REPO = os.path.join(ROOT, "reports")


def main():
    import shutil
    os.makedirs(REPO, exist_ok=True)
    os.makedirs(CONF, exist_ok=True)
    # 幂等清场：旧证据/旧日志清掉（密钥保留复用——日志密钥换新会导致历史检查点验签失败）
    for d in (os.path.join(EVID, "record-001"), LOG_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)

    # 1. 密钥（已存在则复用；私钥仅本地 0600；绝不入证据包/报告）
    if os.path.exists(os.path.join(KEYS, "gadic-author-private-key.pem")):
        author = {"key_id": load_private(
            os.path.join(KEYS, "gadic-author-private-key.pem")).key_id,
            "private_key_path": os.path.join(KEYS, "gadic-author-private-key.pem"),
            "public_key_path": os.path.join(KEYS, "gadic-author-public-key.pem")}
    else:
        author = generate_keypair(KEYS, "gadic-author")
    if os.path.exists(os.path.join(KEYS, "gadic-log-private-key.pem")):
        logkey = {"key_id": load_private(
            os.path.join(KEYS, "gadic-log-private-key.pem")).key_id,
            "private_key_path": os.path.join(KEYS, "gadic-log-private-key.pem"),
            "public_key_path": os.path.join(KEYS, "gadic-log-public-key.pem")}
    else:
        logkey = generate_keypair(KEYS, "gadic-log")
    print("author key_id:", author["key_id"])
    print("log    key_id:", logkey["key_id"])

    # 2. 合成作品（SYNTHETIC——不是真实创作物）
    asset = os.path.join(ROOT, "examples", "synthetic", "work-001.txt")
    os.makedirs(os.path.dirname(asset), exist_ok=True)
    with open(asset, "wb") as f:
        f.write(b"GADIC-PROV-MVP-001 synthetic work sample #1 (demo, not a real work)\n"
                b"line-02\nline-03\n")

    # 3. M1 登记 + M2 签名
    rec = register(asset, os.path.join(EVID, "record-001"),
                   claimant_ref="SYNTHETIC-CLAIMANT-DEMO",
                   media_type="text/plain")
    signed = sign_manifest(rec["manifest_path"], author["private_key_path"],
                           os.path.join(EVID, "record-001"),
                           signed_at_claimed=None)
    print("record_id:", rec["record_id"])
    print("asset_hash:", rec["asset_hash"])
    print("envelope_digest(imprint 对象):", signed["envelope_digest"])

    # 4. M3 时间戳：未配置 TSA → 如实 NOT_CONFIGURED（不生成假令牌）
    ts_status = "NOT_CONFIGURED"

    # 5. M4 透明日志追加（本地篡改检测；非独立第三方见证）
    log = TransparencyLog(LOG_DIR, logkey["private_key_path"])
    ev = log.make_event(event_type="ASSET_REGISTERED",
                        record_id=rec["record_id"],
                        manifest_digest="sha256:" + rec["asset_hash"],
                        signature_digest="sha256:" + signed["envelope_digest"],
                        timestamp_token_digest=None)
    app = log.append_event(ev)
    tdir = os.path.join(EVID, "record-001", "transparency")
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "event.json"), "wb") as f:
        f.write(jcs(ev))
    with open(os.path.join(tdir, "checkpoint.json"), "wb") as f:
        f.write(jcs(app["checkpoint"]))
    with open(os.path.join(tdir, "inclusion-proof.json"), "wb") as f:
        f.write(jcs({"leaf_index": app["leaf_index"], "tree_size": app["tree_size"],
                     "root_hash": app["root_hash"], "path": app["inclusion_proof"]}))
    print("log tree_size:", app["tree_size"], "root:", app["root_hash"][:16], "…")

    # 6. 信任策略（演示：指纹由本脚本带外写入；正式流程须由可信渠道分发）
    with open(os.path.join(CONF, "trust-policy.json"), "wb") as f:
        f.write(jcs({
            "policy_version": "1",
            "trusted_signer_key_ids": [author["key_id"]],
            "trusted_log_key_ids": [logkey["key_id"]],
            "require_tsa": False,
            "note": "DEMO policy; key distribution channel is out-of-band in production",
        }))

    # 7. M5 独立验证（干净输入重放：只用磁盘材料 + 策略）
    res = verify_bundle(
        asset, os.path.join(EVID, "record-001"),
        {"trusted_signer_key_ids": [author["key_id"]],
         "trusted_log_key_ids": [logkey["key_id"]]},
        log_events_path=os.path.join(LOG_DIR, "events.jsonl"),
        log_checkpoints_path=os.path.join(LOG_DIR, "checkpoints.jsonl"),
        log_public_key_path=logkey["public_key_path"],
    )
    report_path = os.path.join(REPO, "verification-report.json")
    with open(report_path, "wb") as f:
        f.write(jcs(res["report"]))
    print("verification:", res["report"]["overall_status"], "exit:", res["exit_code"])

    # 8. 哈希账本（含冻结规范）
    spec_path = os.path.join(ROOT, "specs", "GADIC-PROV-MVP-001-v0.2.0-frozen.md")
    import hashlib
    spec_bytes = open(spec_path, "rb").read()
    hashes = {
        "frozen_spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "frozen_spec_sha1": hashlib.sha1(spec_bytes).hexdigest(),
        "frozen_spec_md5": hashlib.md5(spec_bytes).hexdigest(),
        "frozen_spec_size": len(spec_bytes),
        "manifest_sha256": sha256_bytes(open(os.path.join(EVID, "record-001", "manifest.json"), "rb").read()),
        "envelope_sha256": signed["envelope_digest"],
        "verification_report_sha256": sha256_bytes(open(report_path, "rb").read()),
        "events_jsonl_sha256": sha256_bytes(open(os.path.join(LOG_DIR, "events.jsonl"), "rb").read()),
        "checkpoints_jsonl_sha256": sha256_bytes(open(os.path.join(LOG_DIR, "checkpoints.jsonl"), "rb").read()),
        "asset_sha256": rec["asset_hash"],
    }
    with open(os.path.join(ROOT, "reports", "hashes-2026-11-14.json"), "wb") as f:
        f.write(jcs(hashes))
    print(json.dumps(hashes, indent=2))
    return hashes


if __name__ == "__main__":
    main()

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-86be9029
