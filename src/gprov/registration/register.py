"""M1 创作登记（规范 §4-M1）。

不证明作者身份；不把 mtime 当可信创作时间；声明时间记为 SELF_ASSERTED。
"""
import os
import uuid

from ..canonicalization.canonical import jcs
from .hashing import sha256_file_info

MANIFEST_SCHEMA = "gadic.asset-manifest/1.0"
SOFTWARE = "gadic-prov-mvp"
VERSION = "0.2.0"


def build_manifest(file_path: str, *, claimant_ref=None, claim_type="creation_record",
                   claimed_created_at=None, media_type=None, parent_assets=None,
                   contributors=None) -> dict:
    digest, size = sha256_file_info(file_path)
    return {
        "schema_version": MANIFEST_SCHEMA,
        "record_id": f"urn:uuid:{uuid.uuid4()}",
        "asset": {
            "representation": "original-bytes",
            "media_type": media_type or "application/octet-stream",
            "size_bytes": size,
            "hash": {"algorithm": "sha-256", "value": digest},
        },
        "claim": {
            "claim_type": claim_type,
            "claimant_ref": claimant_ref,
            "claim_status": "SELF_ASSERTED",
            "claimed_created_at": claimed_created_at,
            "rights_holder_claim": None,
            "license_ref": None,
        },
        "contributors": contributors or [],
        "relationships": {
            "parent_assets": parent_assets or [],
            "source_assets": [],
            "derived_from": [],
            "replaces_record": None,
        },
        "canonicalization": {"algorithm": "RFC8785-JCS", "version": "1"},
        "created_by": {"software": SOFTWARE, "version": VERSION},
    }


def register(file_path: str, out_dir: str, **kwargs) -> dict:
    """登记文件：计算摘要 + 生成 manifest（以 JCS 规范字节落盘）。

    返回 {record_id, asset_hash, size_bytes, manifest_path, manifest}。
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)
    manifest = build_manifest(file_path, **kwargs)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.json")
    # manifest.json 即规范字节：文件摘要 == 待签名摘要，杜绝存储变换歧义
    with open(manifest_path, "wb") as f:
        f.write(jcs(manifest))
    return {
        "record_id": manifest["record_id"],
        "asset_hash": manifest["asset"]["hash"]["value"],
        "size_bytes": manifest["asset"]["size_bytes"],
        "manifest_path": manifest_path,
        "manifest": manifest,
    }

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-e0fe31d2
