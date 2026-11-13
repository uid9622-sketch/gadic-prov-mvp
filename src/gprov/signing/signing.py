"""M2 数字签名（规范 §4-M2）：Ed25519（RFC 8032）+ RFC 8785 JCS。

签名对象 = manifest_core 的规范化字节。
私钥落盘仅为 MVP 本地实现（0600 权限）；生产应使用 OS Keychain / 硬件密钥（§10.2）。
"""
import base64
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..canonicalization.canonical import jcs, strict_loads
from ..canonicalization.canonical import DuplicateKeyError  # re-export
from ..registration.hashing import sha256_bytes

ENVELOPE_SCHEMA = "gadic.signature-envelope/1.0"


class KeyMaterial:
    def __init__(self, private=None, public=None):
        self.private = private
        self.public = public

    @property
    def key_id(self) -> str:
        """key_id = SHA-256(Raw 公钥) 十六进制（算法显式记录于 envelope）。"""
        raw = self.public.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return sha256_bytes(raw)

    def public_pem(self) -> bytes:
        return self.public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def generate_keypair(key_dir: str, key_name: str = "gadic-author") -> dict:
    """生成 Ed25519 密钥对；私钥 0600。返回 {key_id, private_key_path, public_key_path}。"""
    os.makedirs(key_dir, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    km = KeyMaterial(private=private, public=private.public_key())
    priv_path = os.path.join(key_dir, f"{key_name}-private-key.pem")
    pub_path = os.path.join(key_dir, f"{key_name}-public-key.pem")
    priv_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    fd = os.open(priv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(priv_pem)
    with open(pub_path, "wb") as f:
        f.write(km.public_pem())
    return {"key_id": km.key_id, "private_key_path": priv_path,
            "public_key_path": pub_path, "algorithm": "Ed25519"}


def load_private(path: str) -> KeyMaterial:
    with open(path, "rb") as f:
        private = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise TypeError("only Ed25519 private keys are supported")
    return KeyMaterial(private=private, public=private.public_key())


def load_public_pem(pem_bytes: bytes) -> KeyMaterial:
    public = serialization.load_pem_public_key(pem_bytes)
    if not isinstance(public, Ed25519PublicKey):
        raise TypeError("only Ed25519 public keys are supported")
    return KeyMaterial(public=public)


def sign_manifest(manifest_path: str, private_key_path: str, out_dir: str,
                  signed_at_claimed=None) -> dict:
    """对 manifest 规范化字节签名，输出 signature-envelope.json（JCS 字节落盘）。"""
    with open(manifest_path, "rb") as f:
        manifest_bytes = f.read()
    # 防御：manifest 必须本身已是规范字节且无重复键
    try:
        manifest = strict_loads(manifest_bytes.decode("utf-8"))
    except DuplicateKeyError:
        raise
    if jcs(manifest) != manifest_bytes:
        raise ValueError("manifest.json is not in canonical (JCS) form")
    km = load_private(private_key_path)
    signature = km.private.sign(manifest_bytes)
    envelope = {
        "schema_version": ENVELOPE_SCHEMA,
        "record_id": manifest["record_id"],
        "manifest_digest": {"algorithm": "sha-256",
                            "value": sha256_bytes(manifest_bytes)},
        "signature": {
            "algorithm": "Ed25519",
            "key_id": km.key_id,
            "value_base64url": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
        },
        "signed_at_claimed": signed_at_claimed,
        "canonicalization": "RFC8785-JCS",
    }
    os.makedirs(out_dir, exist_ok=True)
    env_path = os.path.join(out_dir, "signature-envelope.json")
    with open(env_path, "wb") as f:
        f.write(jcs(envelope))
    pub_path = os.path.join(out_dir, "signer-public-key.pem")
    with open(pub_path, "wb") as f:
        f.write(km.public_pem())
    envelope_path_digest = sha256_bytes(jcs(envelope))
    return {"envelope_path": env_path, "public_key_path": pub_path,
            "key_id": km.key_id,
            "envelope_digest": envelope_path_digest,  # == timestamp_imprint 对象
            "manifest_digest": envelope["manifest_digest"]["value"]}


def verify_signature(manifest_bytes: bytes, signature_b64url: str, public_pem: bytes) -> bool:
    raw = base64.urlsafe_b64decode(signature_b64url + "=" * (-len(signature_b64url) % 4))
    km = load_public_pem(public_pem)
    try:
        km.public.verify(raw, manifest_bytes)
        return True
    except Exception:
        return False

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-46779850
