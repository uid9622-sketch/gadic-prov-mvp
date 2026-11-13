# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-regen_checksums-20261114
"""重算 SHA256SUMS.sha256（保留 DNA 注释行，覆盖全部 git 跟踪文件）。

规矩（写进 RELEASE-CHECKLIST ②）：任何文件改动后、提交前必须跑——
    python scripts/regen_checksums.py && sha256sum -c SHA256SUMS.sha256
"""
import hashlib
import pathlib
import subprocess


def main() -> int:
    sums = pathlib.Path("SHA256SUMS.sha256")
    lines = sums.read_text(encoding="utf-8").splitlines()
    dna = [l for l in lines if l.startswith("#")]
    out = []
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True
    ).stdout.split()
    for f in sorted(files):
        if f == "SHA256SUMS.sha256":
            continue  # 清单不含自身（自引用悖论）
        out.append(f"{hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()}  {f}")
    sums.write_text("\n".join(dna + out) + "\n", encoding="utf-8")
    print(f"SHA256SUMS 重算完成: {len(out)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
