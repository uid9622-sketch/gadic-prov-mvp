"""M4 追加式透明日志（规范 §4-M4）。

- leaf_data 编码 = JCS(event dict)（固定版本，验证器按同规则重放）。
- 每次追加产出新 tree_size/root，并由日志签名密钥签署 checkpoint。
- 同一 tree_size 出现不同 root → LOG_FORK_DETECTED（T-016）。
- 本地日志仅具备本地篡改检测能力，不等于独立第三方见证（§11.3）。
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

from ..canonicalization.canonical import jcs
from ..signing.signing import KeyMaterial, load_private
from .merkle import leaf_hash, tree_root, inclusion_path, verify_inclusion, \
    consistency_proof, verify_consistency

LOG_EVENT_SCHEMA = "gadic.log-event/1.0"


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


class ForkDetected(Exception):
    pass


class TransparencyLog:
    """本地追加式日志。events.jsonl + checkpoints.jsonl + log-private-key.pem。"""

    def __init__(self, log_dir: str, log_key_path: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.events_path = os.path.join(log_dir, "events.jsonl")
        self.checkpoints_path = os.path.join(log_dir, "checkpoints.jsonl")
        self.km = load_private(log_key_path)
        self._leaves = []          # leaf hashes（进程内重建，源自磁盘 leaf_data）
        self._events = []          # event dicts
        self._checkpoints = {}     # tree_size -> {"root_hash","signature","log_key_id","observed_time"}
        if os.path.exists(self.events_path):
            with open(self.events_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        ev = json.loads(line)
                        self._events.append(ev)
                        self._leaves.append(leaf_hash(jcs(ev)))
        if os.path.exists(self.checkpoints_path):
            with open(self.checkpoints_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        cp = json.loads(line)
                        size = cp["tree_size"]
                        if size in self._checkpoints and \
                                self._checkpoints[size]["root_hash"] != cp["root_hash"]:
                            raise ForkDetected(
                                f"LOG_FORK_DETECTED at tree_size={size} (on load)")
                        self._checkpoints[size] = cp

    def sign_checkpoint(self, tree_size: int, root_h: bytes) -> dict:
        cp = {
            "tree_size": tree_size,
            "root_hash": root_h.hex(),
            "log_key_id": self.km.key_id,
            "observed_time": _now_rfc3339(),   # 本机时间，仅观测值，非可信时间
            "signature_algorithm": "Ed25519",
        }
        signed_bytes = jcs({"tree_size": tree_size, "root_hash": cp["root_hash"]})
        cp["signature_base64"] = _b64(self.km.private.sign(signed_bytes))
        return cp

    def append_event(self, event: dict) -> dict:
        """追加事件 → 新检查点。返回 {tree_size, root_hash, inclusion_proof, checkpoint}。"""
        leaf_data = jcs(event)
        self._leaves.append(leaf_hash(leaf_data))
        self._events.append(event)
        size = len(self._leaves)
        root_h = tree_root(self._leaves)
        cp = self.sign_checkpoint(size, root_h)
        if size in self._checkpoints and \
                self._checkpoints[size]["root_hash"] != cp["root_hash"]:
            raise ForkDetected(f"LOG_FORK_DETECTED at tree_size={size}")
        self._checkpoints[size] = cp
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(leaf_data.decode("utf-8") + "\n")
        with open(self.checkpoints_path, "a", encoding="utf-8") as f:
            f.write(jcs(cp).decode("utf-8") + "\n")
        idx = size - 1
        return {
            "event_id": event["event_id"],
            "tree_size": size,
            "root_hash": cp["root_hash"],
            "inclusion_proof": [_b64(h) for h in inclusion_path(self._leaves, idx, 0, size)],
            "leaf_index": idx,
            "checkpoint": cp,
        }

    def make_event(self, *, event_type: str, record_id: str, manifest_digest: str,
                   signature_digest=None, timestamp_token_digest=None,
                   ganzhi: bool = True) -> dict:
        prev = None
        if self._checkpoints:
            last_size = max(self._checkpoints)
            prev = {"tree_size": last_size,
                    "root_hash": self._checkpoints[last_size]["root_hash"]}
        gz = None
        if ganzhi:  # 干支纪时桥（2026-11-14 合并令）；引擎缺席=None 不编造
            from ..time_ganzhi import ganzhi_stamp
            gz = ganzhi_stamp()
        return {
            "schema_version": LOG_EVENT_SCHEMA,
            "event_id": f"urn:uuid:{uuid.uuid4()}",
            "event_type": event_type,
            "record_id": record_id,
            "manifest_digest": manifest_digest,
            "signature_digest": signature_digest,
            "timestamp_token_digest": timestamp_token_digest,
            "event_time_observed": _now_rfc3339(),
            "ganzhi_stamp": gz,  # 文化纪时辅助字段·SELF_ASSERTED·非可信时间
            "previous_checkpoint": prev,
        }

    # ---- 独立验证支持（不依赖登记器内存，仅用磁盘数据重放） ----

    def leaves_from_disk(self):
        return [leaf_hash(jcs(ev)) for ev in self._events]

    def inclusion_proof_for(self, index: int):
        leaves = self.leaves_from_disk()
        size = len(leaves)
        root_h = tree_root(leaves)
        return {
            "leaf_index": index,
            "tree_size": size,
            "root_hash": root_h.hex(),
            "path": [_b64(h) for h in inclusion_path(leaves, index, 0, size)],
        }

    def consistency_proof_for(self, m: int):
        leaves = self.leaves_from_disk()
        n = len(leaves)
        nodes = consistency_proof(leaves, m, n)
        cps = self._checkpoints
        return {
            "m": m, "n": n,
            "proof": [_b64(x) for x in nodes],
            "root_old": cps[m]["root_hash"],
            "root_new": cps[n]["root_hash"],
        }

    def verify_checkpoint_signature(self, cp: dict, public_pem: bytes) -> bool:
        from ..signing.signing import verify_signature as _vs
        signed = jcs({"tree_size": cp["tree_size"], "root_hash": cp["root_hash"]})
        return _vs(signed, cp["signature_base64"], public_pem)

    def verify_inclusion_by_index(self, index: int, public_pem: bytes) -> dict:
        """独立重放：从磁盘事件重算叶子 → 根，并验证包含证明与检查点签名。"""
        leaves = self.leaves_from_disk()
        size = len(leaves)
        root_h = tree_root(leaves)
        proof = self.inclusion_proof_for(index)
        ok = verify_inclusion(index, size, leaves[index], root_h, proof["path"])
        cp = self._checkpoints.get(size)
        cp_ok = bool(cp) and cp["root_hash"] == root_h.hex() and \
            self.verify_checkpoint_signature(cp, public_pem)
        return {"inclusion": ok, "checkpoint_signature": cp_ok,
                "tree_size": size, "root_hash": root_h.hex()}

    def verify_consistency_pair(self, m: int, public_pem: bytes) -> dict:
        res = self.consistency_proof_for(m)
        ok = verify_consistency(m, res["n"], [_unb64(x) for x in res["proof"]],
                                bytes.fromhex(res["root_old"]), bytes.fromhex(res["root_new"]))
        return {"consistency": ok, **res}

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-4e34498e
