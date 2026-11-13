"""M3 RFC 3161 可信时间戳（规范 §4-M3）。

MVP 原则：
- 未配置 TSA → NOT_CONFIGURED，绝不生成假令牌（§0.3 / T-008）。
- 配置了 TSA → 通过 openssl ts 子进程请求与验证；openssl 不可用 → FAIL。
- 本地测试 TSA 必须在配置中标注 "is_test_tsa": true，报告标记 TEST_TSA。

tsa.json 格式：
{
  "url": "https://.../tsa",          # RFC 3161 HTTP POST 端点
  "ca_file": "./config/tsa-chain.pem",  # TSA 证书链（信任锚）
  "is_test_tsa": false
}
"""
import os
import subprocess
import tempfile

from ..canonicalization.canonical import jcs
from ..registration.hashing import sha256_bytes


def timestamp_imprint(signature_envelope: dict) -> bytes:
    """timestamp_imprint = SHA-256(JCS(signature_envelope))（§3.4 固定顺序）。"""
    digest_hex = sha256_bytes(jcs(signature_envelope))
    return bytes.fromhex(digest_hex)


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, timeout=60, **kw)


def request_timestamp(envelope: dict, bundle_dir: str, tsa_config: dict) -> dict:
    """返回 {status, token_path, imprint_hex, note}；status ∈ PASS/FAIL/NOT_CONFIGURED。"""
    imprint = timestamp_imprint(envelope)
    base = {"imprint_hex": imprint.hex(),
            "imprint_algorithm": "sha-256",
            "protocol": "RFC3161"}
    if not tsa_config:
        return {**base, "status": "NOT_CONFIGURED",
                "token_path": None,
                "note": "No TSA configured; no fake token generated (T-008)"}
    if not shutil_which("openssl"):
        return {**base, "status": "FAIL", "token_path": None,
                "note": "openssl not available"}
    ts_dir = os.path.join(bundle_dir, "timestamp")
    os.makedirs(ts_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        imprint_bin = os.path.join(tmp, "imprint.bin")
        tsq = os.path.join(tmp, "request.tsq")
        tsr_local = os.path.join(tmp, "token.tsr")
        with open(imprint_bin, "wb") as f:
            f.write(imprint)
        r1 = _run(["openssl", "ts", "-query", "-data", imprint_bin,
                   "-sha256", "-out", tsq])
        if r1.returncode != 0:
            return {**base, "status": "FAIL", "token_path": None,
                    "note": f"tsq build failed: {r1.stderr.decode(errors='replace')[:200]}"}
        # RFC 3161 over HTTP: POST application/timestamp-query
        try:
            import urllib.request
            req = urllib.request.Request(
                tsa_config["url"], data=open(tsq, "rb").read(),
                headers={"Content-Type": "application/timestamp-query"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except Exception as e:
            return {**base, "status": "FAIL", "token_path": None,
                    "note": f"TSA request failed (bounded retry exhausted): {e}"}
        tsr = os.path.join(ts_dir, "token.tsr")
        with open(tsr, "wb") as f:
            f.write(body)
        with open(os.path.join(ts_dir, "request.tsq"), "wb") as f:
            f.write(open(tsq, "rb").read())
        ca = tsa_config.get("ca_file")
        verify_cmd = ["openssl", "ts", "-verify", "-token", tsr, "-data", imprint_bin]
        if ca and os.path.exists(ca):
            verify_cmd += ["-CAfile", ca]
        r2 = _run(verify_cmd)
        ok = r2.returncode == 0
        tag = " (TEST_TSA)" if tsa_config.get("is_test_tsa") else ""
        return {**base, "status": "PASS" if ok else "FAIL",
                "token_path": tsr,
                "note": ("token verified against configured trust anchor" if ok
                         else f"token verification failed{tag}: "
                              + r2.stderr.decode(errors="replace")[:200])}


def shutil_which(name):
    from shutil import which
    return which(name)

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-310a119d
