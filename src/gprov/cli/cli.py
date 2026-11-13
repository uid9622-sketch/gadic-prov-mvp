"""gprov CLI（规范 §7.1 契约的 MVP 实现）。

命令：keys / register / inspect / sign / timestamp / log / verify
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from gprov.canonicalization.canonical import jcs, strict_loads
from gprov.registration.register import register
from gprov.registration.hashing import sha256_bytes
from gprov.signing.signing import generate_keypair, sign_manifest, load_public_pem
from gprov.transparency.transparency import TransparencyLog, ForkDetected
from gprov.timestamping.rfc3161 import request_timestamp
from gprov.verification.verifier import verify_bundle

def _repo_root() -> str:
    """仓根解析：GPROV_HOME 环境变量优先；否则从本文件向上找含 pyproject.toml 的目录。

    不再硬编码本机路径（2026-11-14 CI 适配：/home/runner 等环境同样可用）。
    """
    env = os.environ.get("GPROV_HOME")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))  # <repo>/src/gprov/cli
    for _ in range(6):
        if os.path.exists(os.path.join(here, "pyproject.toml")):
            return here
        nxt = os.path.dirname(here)
        if nxt == here:
            break
        here = nxt
    return os.getcwd()


REPO = _repo_root()
KEYS = os.path.join(REPO, "keys")
LOG_DIR = os.path.join(REPO, "evidence", "transparency-log")


def cmd_keys(args):
    info = generate_keypair(KEYS, args.key_name)
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_register(args):
    out = register(args.file, args.out, claimant_ref=args.claimant,
                   claim_type=args.claim_type, media_type=args.media_type)
    print(json.dumps({k: out[k] for k in
                      ("record_id", "asset_hash", "size_bytes", "manifest_path")},
                     indent=2, ensure_ascii=False))


def cmd_inspect(args):
    with open(args.manifest, "rb") as f:
        raw = f.read()
    m = strict_loads(raw.decode("utf-8"))
    print(json.dumps({
        "record_id": m["record_id"],
        "asset_hash": m["asset"]["hash"]["value"],
        "size_bytes": m["asset"]["size_bytes"],
        "canonical_sha256": sha256_bytes(raw),
        "is_canonical_bytes": jcs(m) == raw,
    }, indent=2, ensure_ascii=False))


def cmd_sign(args):
    key_path = args.key_path or os.path.join(KEYS, "gadic-author-private-key.pem")
    res = sign_manifest(args.manifest, key_path, args.record_dir)
    print(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_timestamp(args):
    bundle = args.record_dir
    with open(os.path.join(bundle, "signature-envelope.json"), "rb") as f:
        envelope = strict_loads(f.read().decode("utf-8"))
    cfg = None
    if args.tsa_config and os.path.exists(args.tsa_config):
        with open(args.tsa_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    res = request_timestamp(envelope, bundle, cfg)
    print(json.dumps(res, indent=2, ensure_ascii=False))


def _log_key_path():
    return os.path.join(KEYS, "gadic-log-private-key.pem")


def cmd_log(args):
    log = TransparencyLog(LOG_DIR, _log_key_path())
    if args.action == "append":
        bundle = args.record_dir
        with open(os.path.join(bundle, "manifest.json"), "rb") as f:
            manifest = strict_loads(f.read().decode("utf-8"))
        env_path = os.path.join(bundle, "signature-envelope.json")
        sig_digest = None
        if os.path.exists(env_path):
            with open(env_path, "rb") as f:
                sig_digest = "sha256:" + sha256_bytes(f.read())
        ev = log.make_event(
            event_type="ASSET_REGISTERED",
            record_id=manifest["record_id"],
            manifest_digest="sha256:" + manifest["asset"]["hash"]["value"],
            signature_digest=sig_digest,
        )
        res = log.append_event(ev)
        # 证据包落盘 transparency 子目录
        tdir = os.path.join(bundle, "transparency")
        os.makedirs(tdir, exist_ok=True)
        with open(os.path.join(tdir, "event.json"), "wb") as f:
            f.write(jcs(ev))
        with open(os.path.join(tdir, "checkpoint.json"), "wb") as f:
            f.write(jcs(res["checkpoint"]))
        with open(os.path.join(tdir, "inclusion-proof.json"), "wb") as f:
            f.write(jcs({"leaf_index": res["leaf_index"],
                         "tree_size": res["tree_size"],
                         "root_hash": res["root_hash"],
                         "path": res["inclusion_proof"]}))
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.action == "proofs":
        res = log.inclusion_proof_for(args.index)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.action == "checkpoint":
        print(json.dumps(log._checkpoints[max(log._checkpoints)],
                         indent=2, ensure_ascii=False))


def cmd_verify(args):
    policy = {}
    if args.trust_policy and os.path.exists(args.trust_policy):
        with open(args.trust_policy, "r", encoding="utf-8") as f:
            policy = json.load(f)
    res = verify_bundle(
        args.asset, args.bundle, policy,
        log_events_path=args.log_events or os.path.join(LOG_DIR, "events.jsonl"),
        log_checkpoints_path=args.log_checkpoints or os.path.join(LOG_DIR, "checkpoints.jsonl"),
        log_public_key_path=args.log_pubkey or os.path.join(KEYS, "gadic-log-public-key.pem"),
    )
    report = res["report"]
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(jcs(report).decode("utf-8"))
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"== gprov 独立验证报告 ==")
        for k, v in report["checks"].items():
            print(f"  {k:22s} {v}")
        print(f"  overall: {report['overall_status']}")
        for lim in report["limitations"]:
            print(f"  [限制] {lim}")
        for e, msg in report["errors"].items():
            print(f"  [错误] {e}: {msg}")
    sys.exit(res["exit_code"])


def main():
    p = argparse.ArgumentParser(prog="gprov",
                                description="GADIC-PROV-MVP-001 gprov CLI v0.2.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("keys")
    s.add_argument("--key-name", default="gadic-author")
    s.set_defaults(func=cmd_keys)

    s = sub.add_parser("register")
    s.add_argument("file"); s.add_argument("--out", required=True)
    s.add_argument("--claimant", default=None)
    s.add_argument("--claim-type", default="creation_record")
    s.add_argument("--media-type", default=None)
    s.set_defaults(func=cmd_register)

    s = sub.add_parser("inspect"); s.add_argument("manifest")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("sign"); s.add_argument("manifest")
    s.add_argument("--record-dir", required=True)
    s.add_argument("--key-path", default=None)
    s.set_defaults(func=cmd_sign)

    s = sub.add_parser("timestamp"); s.add_argument("record_dir")
    s.add_argument("--tsa-config", default=None)
    s.set_defaults(func=cmd_timestamp)

    s = sub.add_parser("log"); s.add_argument("action",
                                              choices=["append", "proofs", "checkpoint"])
    s.add_argument("--record-dir", default=None)
    s.add_argument("--index", type=int, default=0)
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("verify"); s.add_argument("asset"); s.add_argument("bundle")
    s.add_argument("--trust-policy", default=None)
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--out", default=None)
    s.add_argument("--log-events", default=None)
    s.add_argument("--log-checkpoints", default=None)
    s.add_argument("--log-pubkey", default=None)
    s.set_defaults(func=cmd_verify)

    args = p.parse_args()
    try:
        args.func(args)
    except ForkDetected as e:
        print(f"SECURITY_EVENT: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-a1c10943
