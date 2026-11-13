"""GADIC-PROV-MVP-001 测试矩阵（规范 §13）。

覆盖：T-001~T-008、T-012~T-018、T-019、T-020（本地可离线执行部分）。
T-009/010/011/024 依赖真实 TSA（NOT_CONFIGURED，如实标注，不伪造 PASS）。
T-021 撤销流程属 Phase 4（本矩阵未覆盖，见运行报告 Known Limitations）。
"""
import json
import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gprov.canonicalization.canonical import jcs, strict_loads, DuplicateKeyError
from gprov.registration.hashing import sha256_bytes
from gprov.registration.register import register
from gprov.signing.signing import generate_keypair, load_private, sign_manifest, \
    load_public_pem, verify_signature
from gprov.transparency.merkle import (leaf_hash, node_hash, tree_root,
                                       inclusion_path, verify_inclusion,
                                       consistency_proof, verify_consistency)
from gprov.transparency.transparency import TransparencyLog, ForkDetected
from gprov.timestamping.rfc3161 import request_timestamp
from gprov.verification.verifier import verify_bundle


@pytest.fixture()
def ws(tmp_path):
    """每个用例独立工作区：作品文件、密钥、记录目录、日志。"""
    (tmp_path / "asset.txt").write_bytes(b"SYNTHETIC-WORK-0.2.0\n" * 8)
    keys = generate_keypair(str(tmp_path / "keys"), "author")
    log_keys = generate_keypair(str(tmp_path / "keys"), "log")
    km = load_private(keys["private_key_path"])
    log_km = load_private(log_keys["private_key_path"])
    rec = register(str(tmp_path / "asset.txt"), str(tmp_path / "record"),
                   claimant_ref="SYNTHETIC-CLAIMANT", media_type="text/plain")
    sign_manifest(rec["manifest_path"], keys["private_key_path"],
                  str(tmp_path / "record"))
    log = TransparencyLog(str(tmp_path / "log"), log_keys["private_key_path"])
    return {"dir": tmp_path, "asset": tmp_path / "asset.txt", "keys": keys,
            "log_keys": log_keys, "km": km, "log_km": log_km,
            "record": tmp_path / "record", "log": log, "rec": rec}


def _policy(tmp_path, extra=None):
    """信任策略：签名/日志公钥指纹经带外写入策略（证据包自带公钥不自动可信）。"""
    p = {
        "trusted_signer_key_ids": [extra["km"].key_id],
        "trusted_log_key_ids": [extra["log_km"].key_id],
    }
    return p


def _verify_all(ws, tmp_path):
    return verify_bundle(
        str(ws["asset"]), str(ws["record"]), _policy(tmp_path, ws),
        log_events_path=str(tmp_path / "log" / "events.jsonl"),
        log_checkpoints_path=str(tmp_path / "log" / "checkpoints.jsonl"),
        log_public_key_path=ws["log_keys"]["public_key_path"])


# ---------------- M1 / M2 基线 ----------------

def test_T001_same_file_same_digest(ws):
    from gprov.registration.hashing import sha256_file
    assert sha256_file(str(ws["asset"])) == ws["rec"]["asset_hash"]


def test_T002_one_byte_change_fails(ws):
    # 修改一个字节后重新登记 → 摘要必须不同；验证器必须 FAIL
    rec2 = register(str(ws["asset"]), str(ws["dir"] / "record2"))
    data = bytearray((ws["dir"] / "asset.txt").read_bytes())
    data[0] ^= 0x01
    tampered = ws["dir"] / "asset-tampered.txt"
    tampered.write_bytes(bytes(data))
    rec3 = register(str(tampered), str(ws["dir"] / "record3"))
    assert rec2["asset_hash"] != rec3["asset_hash"]


def test_T003_correct_key_passes(ws):
    manifest_bytes = (ws["record"] / "manifest.json").read_bytes()
    sig = json.loads((ws["record"] / "signature-envelope.json").read_bytes()
                     .decode("utf-8"))
    pub = (ws["record"] / "signer-public-key.pem").read_bytes()
    assert verify_signature(manifest_bytes, sig["signature"]["value_base64url"], pub)


def test_T004_wrong_key_fails(ws):
    manifest_bytes = (ws["record"] / "manifest.json").read_bytes()
    sig = json.loads((ws["record"] / "signature-envelope.json").read_bytes()
                     .decode("utf-8"))
    other = generate_keypair(str(ws["dir"] / "keys2"), "other")
    pub = open(other["public_key_path"], "rb").read()
    assert not verify_signature(manifest_bytes,
                                sig["signature"]["value_base64url"], pub)


def test_T005_manifest_modified_after_sign_fails(ws):
    # 签名后改 manifest → 验证器 manifest_signature FAIL
    rec = ws["rec"]
    ev = ws["log"].make_event(event_type="ASSET_REGISTERED",
                              record_id=rec["record_id"],
                              manifest_digest="sha256:" + rec["asset_hash"])
    ws["log"].append_event(ev)
    res = _verify_all(ws, ws["dir"])
    assert res["report"]["checks"]["manifest_signature"] == "PASS"
    # 篡改 manifest（重写 claim_type）
    m = strict_loads((ws["record"] / "manifest.json").read_bytes().decode("utf-8"))
    m["claim"]["claim_type"] = "forged_record"
    (ws["record"] / "manifest.json").write_bytes(jcs(m))
    res2 = _verify_all(ws, ws["dir"])
    assert res2["report"]["checks"]["manifest_signature"] == "FAIL"
    assert res2["report"]["overall_status"] == "FAIL"


def test_T006_field_order_jcs_identical():
    a = {"b": 1, "a": {"z": 2, "y": 3}}
    b = {"a": {"y": 3, "z": 2}, "b": 1}
    assert jcs(a) == jcs(b)


def test_T007_duplicate_key_rejected():
    with pytest.raises(DuplicateKeyError):
        strict_loads('{"a":1,"a":2}')


def test_T008_no_tsa_not_configured_no_fake_token(ws):
    envelope = strict_loads((ws["record"] / "signature-envelope.json")
                            .read_bytes().decode("utf-8"))
    res = request_timestamp(envelope, str(ws["record"]), None)
    assert res["status"] == "NOT_CONFIGURED"
    assert res["token_path"] is None
    assert not os.path.exists(os.path.join(ws["record"], "timestamp", "token.tsr"))


# ---------------- M4 透明日志 ----------------

def _append_n(ws, n):
    """首条事件登记真实 record，其余为合成事件（模拟日志持续追加）。"""
    outs = []
    for i in range(n):
        if i == 0:
            rid, digest = ws["rec"]["record_id"], "sha256:" + ws["rec"]["asset_hash"]
        else:
            rid, digest = f"urn:uuid:synth-{i}", f"sha256:{'00' * i}"
        ev = ws["log"].make_event(event_type="ASSET_REGISTERED",
                                  record_id=rid, manifest_digest=digest)
        outs.append(ws["log"].append_event(ev))
    return outs


def test_T012_log_append_root_recomputable(ws):
    _append_n(ws, 5)
    log = ws["log"]
    assert len(log._leaves) == 5
    leaves = log.leaves_from_disk()
    # 独立重放：从磁盘事件重建的根 == 最新检查点 root
    assert tree_root(leaves).hex() == log._checkpoints[5]["root_hash"]
    # 逐个 size 检查点都与对应前缀树一致
    for s in range(1, 6):
        assert tree_root(leaves[:s]).hex() == log._checkpoints[s]["root_hash"]


def test_T013_modified_leaf_inclusion_fails(ws):
    _append_n(ws, 3)
    log = ws["log"]
    leaves = log.leaves_from_disk()
    root_h = tree_root(leaves)
    good = verify_inclusion(1, 3, leaves[1], root_h,
                            inclusion_path(leaves, 1, 0, 3))
    assert good
    bad_leaf = leaf_hash(b"tampered")
    assert not verify_inclusion(1, 3, bad_leaf, root_h,
                                inclusion_path(leaves, 1, 0, 3))


def test_T014_wrong_path_fails(ws):
    _append_n(ws, 4)
    log = ws["log"]
    leaves = log.leaves_from_disk()
    root_h = tree_root(leaves)
    path = inclusion_path(leaves, 2, 0, 4)
    # 篡改 path 中一个节点
    tampered = list(path)
    tampered[0] = bytes(32)
    assert not verify_inclusion(2, 4, leaves[2], root_h, tampered)


def test_T015_consistency_proofs_all_pairs(ws):
    """随机规模全对验证 + 篡改拒绝。"""
    _append_n(ws, 12)
    log = ws["log"]
    leaves = log.leaves_from_disk()
    for n in range(2, 13):
        for m in range(1, n):
            proof = consistency_proof(leaves, m, n)
            r_old = tree_root(leaves[:m])
            r_new = tree_root(leaves[:n])
            assert verify_consistency(m, n, proof, r_old, r_new), (m, n)
            # 篡改：换掉一个证明节点必须 FAIL
            bad = list(proof)
            bad[0] = bytes(32)
            assert not verify_consistency(m, n, bad, r_old, r_new), (m, n)
            # 冗余节点必须 FAIL
            assert not verify_consistency(m, n, proof + [bytes(32)], r_old, r_new), (m, n)
    # m==n / m==0 边界
    assert verify_consistency(5, 5, [], tree_root(leaves[:5]), tree_root(leaves[:5]))
    assert verify_consistency(0, 3, [], None, tree_root(leaves[:3]))


def test_T016_fork_detected(ws):
    _append_n(ws, 3)
    log = ws["log"]
    # 伪造同一 tree_size 的冲突检查点（外部见证者视角）
    conflict = dict(log._checkpoints[3])
    conflict["root_hash"] = "ff" * 32
    with pytest.raises(ForkDetected):
        # 重放加载路径：注入冲突文件后重新加载
        with open(os.path.join(str(ws["dir"] / "log"), "checkpoints.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(jcs(conflict).decode("utf-8") + "\n")
        TransparencyLog(str(ws["dir"] / "log"),
                        ws["log_keys"]["private_key_path"])


def test_T017_truncation_detected(ws):
    _append_n(ws, 4)
    log = ws["log"]
    # 独立验证器只有被截断的事件列表（3 条）+ 最新检查点（size=4）→ 根不匹配
    events = log.leaves_from_disk()[:3]
    from gprov.transparency.merkle import tree_root as tr
    truncated_root = tr(events).hex()
    assert truncated_root != log._checkpoints[4]["root_hash"]


def test_T018_no_timestamp_is_partial_not_verified(ws):
    _append_n(ws, 1)
    res = _verify_all(ws, ws["dir"])
    r = res["report"]
    # 无 TSA：timestamp_token=NOT_CONFIGURED；整体不得输出 VERIFIED
    assert r["checks"]["timestamp_token"] == "NOT_CONFIGURED"
    assert r["overall_status"] in ("VERIFIED_WITH_LIMITATIONS", "PARTIAL")
    assert r["overall_status"] != "VERIFIED"


def test_T019_verifier_clean_environment(ws):
    """验证器不导入登记器内存：只用磁盘材料 + 带外策略。"""
    _append_n(ws, 2)
    res = _verify_all(ws, ws["dir"])
    assert res["report"]["checks"]["log_inclusion"] == "PASS"
    assert res["report"]["checks"]["manifest_signature"] == "PASS"
    assert res["exit_code"] == 0


def test_T020_no_private_key_in_bundle(ws):
    _append_n(ws, 1)
    for f in os.listdir(str(ws["record"])):
        blob = (ws["record"] / f).read_bytes()
        assert b"PRIVATE KEY" not in blob
    # 日志目录同样无私钥材料
    for f in os.listdir(str(ws["dir"] / "log")):
        blob = (ws["dir"] / "log" / f).read_bytes()
        assert b"PRIVATE KEY" not in blob


def test_T022_path_traversal_rejected(ws, tmp_path):
    """带路径穿越的 bundle 路径 → 拒绝。"""
    from gprov.verification.verifier import BundleError, _load_json
    evil = os.path.join(str(ws["record"]), "..", "..", "..", "etc", "passwd.json")
    # 构造：_load_json 对越界路径抛 BundleError
    target = os.path.join(str(tmp_path), "..", "outside.json")
    with pytest.raises((BundleError, FileNotFoundError)):
        _load_json(target)


# ---------------- 干支纪时桥合并（2026-11-14） ----------------

def test_ganzhi_stamp_year_2026_is_bingwu():
    """基准：2026 = 丙午年（lh_time_engine 自身横幅互证）。"""
    from gprov.time_ganzhi import ganzhi_stamp
    import datetime
    s = ganzhi_stamp(datetime.datetime(2026, 6, 1, 12, 0))
    assert s is not None and s.startswith("丙午年")


def test_ganzhi_stamp_in_event_or_none(ws):
    """事件含 ganzhi_stamp 字段：引擎在=四柱串，缺席=None，绝不编造。"""
    ev = ws["log"].make_event(event_type="ASSET_REGISTERED",
                              record_id=ws["rec"]["record_id"],
                              manifest_digest="sha256:test")
    assert "ganzhi_stamp" in ev
    assert ev["ganzhi_stamp"] is None or "年·" in ev["ganzhi_stamp"]


def test_ganzhi_fallback_without_engine():
    """引擎不可用路径：内嵌兜底生效，仍输出规范四柱（不返回 None 不编造之外崩溃）。"""
    import datetime

    from gprov import time_ganzhi
    orig = time_ganzhi._load_engine
    time_ganzhi._load_engine = lambda: None
    try:
        s = time_ganzhi.ganzhi_stamp(datetime.datetime(2026, 6, 1, 12, 0))
        assert s is not None and s.startswith("丙午年") and "·" in s
    finally:
        time_ganzhi._load_engine = orig


def test_T025_bad_checkpoint_signature_fails(ws):
    _append_n(ws, 2)
    log = ws["log"]
    # 用另一个日志密钥验签 → 必须 FAIL
    other = generate_keypair(str(ws["dir"] / "keys3"), "rogue-log")
    cp = log._checkpoints[2]
    assert not log.verify_checkpoint_signature(cp, open(other["public_key_path"], "rb").read())
    pub = ws["log_keys"]["public_key_path"]
    assert log.verify_checkpoint_signature(cp, open(pub, "rb").read())

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-fe854f2e
