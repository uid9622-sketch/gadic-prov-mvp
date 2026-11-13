"""M5 独立验证器（规范 §4-M5 / §8）。

原则：
- 不导入登记器数据库状态，不依赖登记器进程内存（T-019）；
- 不信任证据包自带公钥——按 Trust Policy 的 key_id 指纹判定（E_KEY_UNTRUSTED）；
- 所有摘要/签名/证明独立重算；
- 离线优先；在线依赖（撤销查询）标 UNKNOWN。
"""
import base64
import json
import os

from ..canonicalization.canonical import jcs, strict_loads, DuplicateKeyError
from ..registration.hashing import sha256_bytes, sha256_file_info
from ..signing.signing import verify_signature
from ..transparency.merkle import leaf_hash, verify_inclusion, verify_consistency

REPORT_SCHEMA = "gadic.verification-report/1.0"
VERIFIER_NAME = "gprov-verify"
VERIFIER_VERSION = "0.2.0"

STATUSES = {"PASS", "PARTIAL", "NOT_RUN", "NOT_CONFIGURED", "UNKNOWN", "FAIL"}

MANIFEST_SCHEMA = "gadic.asset-manifest/1.0"
ENVELOPE_SCHEMA = "gadic.signature-envelope/1.0"
EVENT_SCHEMA = "gadic.log-event/1.0"

EXIT_OK, EXIT_FAIL, EXIT_INCOMPLETE, EXIT_CONFIG, EXIT_SECURITY = 0, 1, 2, 3, 4


class BundleError(Exception):
    pass


def _load_json(path: str):
    """严格解析（拒绝重复键 + 路径穿越防护由调用方保证目录边界）。"""
    real = os.path.realpath(path)
    base = os.path.realpath(os.path.join(os.path.dirname(path), ".."))
    if not real.startswith(base + os.sep) and os.path.dirname(real) != base:
        raise BundleError("path traversal rejected")
    with open(path, "r", encoding="utf-8") as f:
        return strict_loads(f.read())


def _b64(b): return base64.b64encode(b).decode("ascii")
def _unb64(s): return base64.b64decode(s)


def verify_bundle(asset_path: str, bundle_dir: str, trust_policy: dict,
                  log_events_path: str = None, log_checkpoints_path: str = None,
                  log_public_key_path: str = None) -> dict:
    """独立验证。返回 {checks, overall_status, limitations, exit_code, errors}。"""
    checks = {
        "content_hash": "NOT_RUN",
        "manifest_schema": "NOT_RUN",
        "manifest_signature": "NOT_RUN",
        "timestamp_token": "NOT_CONFIGURED",
        "log_inclusion": "NOT_RUN",
        "log_consistency": "NOT_RUN",
        "revocation": "UNKNOWN",
    }
    errors = {}
    limitations = []
    security_event = False

    # ---- 输入解析（沙箱式严格解析） ----
    try:
        manifest = _load_json(os.path.join(bundle_dir, "manifest.json"))
        envelope = _load_json(os.path.join(bundle_dir, "signature-envelope.json"))
    except (DuplicateKeyError, BundleError, FileNotFoundError, json.JSONDecodeError) as e:
        checks["manifest_schema"] = "FAIL"
        return _finish(checks, limitations, errors, security_event,
                       error=f"E_INPUT_INVALID: {e}")

    # ---- manifest schema ----
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        checks["manifest_schema"] = "FAIL"
        errors["manifest_schema"] = f"E_SCHEMA_UNSUPPORTED: {manifest.get('schema_version')}"
        return _finish(checks, limitations, errors, security_event)
    required = ("record_id", "asset", "claim", "canonicalization")
    if not all(k in manifest for k in required):
        checks["manifest_schema"] = "FAIL"
        errors["manifest_schema"] = "E_INPUT_INVALID: missing required fields"
        return _finish(checks, limitations, errors, security_event)
    checks["manifest_schema"] = "PASS"

    # ---- content hash（T-002） ----
    if not os.path.isfile(asset_path):
        checks["content_hash"] = "FAIL"
        errors["content_hash"] = f"asset file not found: {asset_path}"
    else:
        digest, size = sha256_file_info(asset_path)
        declared = manifest["asset"]["hash"]["value"]
        if manifest["asset"]["hash"]["algorithm"] != "sha-256":
            checks["content_hash"] = "FAIL"
            errors["content_hash"] = "unsupported hash algorithm"
        elif manifest["asset"]["size_bytes"] != size:
            checks["content_hash"] = "FAIL"
            errors["content_hash"] = f"E_HASH_MISMATCH: size {size} != {manifest['asset']['size_bytes']}"
        elif digest == declared:
            checks["content_hash"] = "PASS"
        else:
            checks["content_hash"] = "FAIL"
            errors["content_hash"] = "E_HASH_MISMATCH"

    # ---- manifest signature（T-003/T-004/T-005） ----
    manifest_bytes = jcs(manifest)
    sig = envelope.get("signature", {})
    pub_path = os.path.join(bundle_dir, "signer-public-key.pem")
    if envelope.get("schema_version") != ENVELOPE_SCHEMA:
        checks["manifest_signature"] = "FAIL"
        errors["manifest_signature"] = "E_SCHEMA_UNSUPPORTED (envelope)"
    elif envelope.get("manifest_digest", {}).get("value") != sha256_bytes(manifest_bytes):
        checks["manifest_signature"] = "FAIL"
        errors["manifest_signature"] = "E_SIGNATURE_INVALID: manifest digest mismatch"
    elif not os.path.exists(pub_path):
        checks["manifest_signature"] = "UNKNOWN"
        errors["manifest_signature"] = "E_KEY_UNTRUSTED: signer public key missing"
    else:
        with open(pub_path, "rb") as f:
            pub_pem = f.read()
        # 信任判定：公钥指纹必须在信任策略列表内；证据包自带公钥不自动可信（§4-M5）
        from ..signing.signing import load_public_pem
        km = load_public_pem(pub_pem)
        trusted_ids = trust_policy.get("trusted_signer_key_ids", [])
        if km.key_id not in trusted_ids:
            checks["manifest_signature"] = "UNKNOWN"
            errors["manifest_signature"] = "E_KEY_UNTRUSTED: key_id not in trust policy"
        elif verify_signature(manifest_bytes, sig.get("value_base64url", ""), pub_pem):
            checks["manifest_signature"] = "PASS"
        else:
            checks["manifest_signature"] = "FAIL"
            errors["manifest_signature"] = "E_SIGNATURE_INVALID"

    # ---- timestamp（T-008 如实降级） ----
    ts_dir = os.path.join(bundle_dir, "timestamp")
    token_path = os.path.join(ts_dir, "token.tsr")
    if trust_policy.get("timestamp_token_path"):
        checks["timestamp_token"] = "UNKNOWN"  # MVP 不在验证器内重跑 openssl；见 note
        limitations.append("timestamp token present; verify with gprov timestamp path")
    elif os.path.exists(token_path):
        checks["timestamp_token"] = "UNKNOWN"
        limitations.append("token.tsr present but no trust anchor configured in policy")
    else:
        checks["timestamp_token"] = "NOT_CONFIGURED"
        limitations.append("no RFC 3161 token; NOT_CONFIGURED per T-008 (no fake PASS)")

    # ---- log inclusion + checkpoint signature（T-013/T-014/T-025） ----
    if log_events_path and log_checkpoints_path and log_public_key_path:
        try:
            events = []
            with open(log_events_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(strict_loads(line))
            cps = []
            with open(log_checkpoints_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        cps.append(strict_loads(line))
            with open(log_public_key_path, "rb") as f:
                log_pub_pem = f.read()
            from ..signing.signing import load_public_pem
            log_km = load_public_pem(log_pub_pem)
            trusted_log_ids = trust_policy.get("trusted_log_key_ids", [])

            # 找到本 record 的事件
            ev_idx = None
            for i, ev in enumerate(events):
                if ev.get("record_id") == manifest["record_id"] and \
                        ev.get("schema_version") == EVENT_SCHEMA:
                    ev_idx = i
                    break
            if ev_idx is None:
                checks["log_inclusion"] = "FAIL"
                errors["log_inclusion"] = "event for record_id not found in log"
            else:
                # 树一致性：每个检查点 root 必须可由磁盘事件重放得出
                leaves = [leaf_hash(jcs(ev)) for ev in events]
                from ..transparency.merkle import tree_root
                max_size = len(leaves)
                size_to_root = {}
                fork = False
                for cp in cps:
                    s = cp["tree_size"]
                    r = cp["root_hash"]
                    if s in size_to_root and size_to_root[s] != r:
                        fork = True
                    size_to_root[s] = r
                # 验证检查点签名（日志公钥须受信）
                cp_sigs_ok = all(
                    log_km.key_id in trusted_log_ids and
                    verify_signature(
                        jcs({"tree_size": cp["tree_size"],
                             "root_hash": cp["root_hash"]}),
                        cp["signature_base64"], log_pub_pem)
                    for cp in cps)
                # 最新 root 重放
                current_root = tree_root(leaves)
                latest_cp = max(cps, key=lambda c: c["tree_size"]) if cps else None
                root_ok = bool(latest_cp) and latest_cp["tree_size"] == max_size and \
                    latest_cp["root_hash"] == current_root.hex()
                if fork:
                    checks["log_inclusion"] = "FAIL"
                    errors["log_inclusion"] = "E_LOG_FORK: conflicting roots for same tree_size"
                    security_event = True
                elif not (cp_sigs_ok and root_ok):
                    checks["log_inclusion"] = "FAIL"
                    errors["log_inclusion"] = (
                        "E_LOG_PROOF_INVALID: checkpoint signature" if not cp_sigs_ok
                        else "checkpoint root does not match recomputed tree (truncation/rewrite?)")
                else:
                    from ..transparency.merkle import inclusion_path
                    path = inclusion_path(leaves, ev_idx, 0, max_size)
                    if verify_inclusion(ev_idx, max_size, leaves[ev_idx],
                                        current_root, path):
                        checks["log_inclusion"] = "PASS"
                    else:
                        checks["log_inclusion"] = "FAIL"
                        errors["log_inclusion"] = "E_LOG_PROOF_INVALID (inclusion)"
                # consistency proof（T-015）：验证器对每一对相邻检查点独立重放
                if checks["log_inclusion"] == "PASS":
                    sizes = sorted(size_to_root)
                    cons_ok = True
                    if len(sizes) >= 2:
                        for m in sizes[:-1]:
                            n = sizes[sizes.index(m) + 1]
                            from ..transparency.merkle import consistency_proof
                            proof = consistency_proof(leaves, m, n)
                            if not verify_consistency(m, n, proof,
                                                      bytes.fromhex(size_to_root[m]),
                                                      bytes.fromhex(size_to_root[n])):
                                cons_ok = False
                                break
                    checks["log_consistency"] = "PASS" if cons_ok else "FAIL"
                    if not cons_ok:
                        errors["log_consistency"] = "E_LOG_PROOF_INVALID (consistency)"
                else:
                    checks["log_consistency"] = "NOT_RUN"
        except FileNotFoundError as e:
            checks["log_inclusion"] = "UNKNOWN"
            errors["log_inclusion"] = f"log material missing: {e}"
    else:
        checks["log_inclusion"] = "UNKNOWN"
        errors["log_inclusion"] = "E_POLICY_UNAVAILABLE: log material paths not provided"

    return _finish(checks, limitations, errors, security_event)


def _finish(checks, limitations, errors, security_event, error=None):
    if error:
        errors["input"] = error
    required_fail = any(checks[k] == "FAIL" for k in
                        ("content_hash", "manifest_schema", "manifest_signature",
                         "log_inclusion", "log_consistency"))
    all_pass = all(checks[k] == "PASS" for k in
                   ("content_hash", "manifest_schema", "manifest_signature",
                    "log_inclusion", "log_consistency"))
    optional_missing = any(checks[k] in ("NOT_CONFIGURED", "NOT_RUN", "UNKNOWN", "PARTIAL")
                           for k in ("timestamp_token", "log_consistency", "revocation"))
    if security_event or required_fail:
        overall = "FAIL"
        code = EXIT_SECURITY if security_event else EXIT_FAIL
    elif all_pass and not optional_missing:
        overall, code = "VERIFIED", EXIT_OK
    elif all_pass:
        overall, code = "VERIFIED_WITH_LIMITATIONS", EXIT_OK
    else:
        overall, code = "PARTIAL", EXIT_INCOMPLETE
    report = {
        "schema_version": REPORT_SCHEMA,
        "verifier": {"name": VERIFIER_NAME, "version": VERIFIER_VERSION},
        "checks": checks,
        "overall_status": overall,
        "limitations": limitations,
        "errors": errors,
    }
    return {"report": report, "exit_code": code, "security_event": security_event}

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-c3faad33
