"""GADIC-PROV-MVP 批量 DNA 盖章 + SHA256 清单（"代码都要弄 sha256 才上传"令）。

规则：
- 每个文本文件独立生成 DNA（真身 = longhun-system/08_BIN/lh_dna_generator.py）；
- .py/.toml 追加 `# DNA行`；.md 追加 `<!-- DNA行 -->`；
- 幂等：已有 #龍芯⚡️ 标记的文件跳过；
- 盖章后生成 SHA256SUMS.sha256（头部带 DNA 注释，sha256sum -c 可校验）；
- 冻结规范盖章 → 字节变化 → 按规范 §16 回填说明规则记 v0.2.0-hashfix 重算哈希。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "#龍芯⚡️"


def gen_dna_line(title: str, category: str = "代码") -> str:
    """返回形如 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-6214abf5 的单行。"""
    r = subprocess.run(
        ["python3", "/Users/zuimeidedeyihan/longhun-system/08_BIN/lh_dna_generator.py",
         "generate", "--title", title, "--category", category,
         "--actor", "AUTHOR-ID", "--format", "text"],
        capture_output=True, text=True, timeout=30)
    for line in r.stdout.splitlines():
        if MARKER in line:
            return line.strip()
    raise RuntimeError(f"DNA generation failed for {title}")


def iter_files():
    skip_dirs = {"__pycache__", ".pytest_cache", ".git", "keys", "node_modules"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if fn.endswith((".py", ".md", ".toml")):
                yield os.path.join(dirpath, fn)


def main():
    stamped, skipped = [], []
    for path in sorted(iter_files()):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if MARKER in content:
            skipped.append(path)
            continue
        rel = os.path.relpath(path, ROOT)
        dna = gen_dna_line(rel, "代码" if path.endswith(".py") else "文档")
        if path.endswith(".md"):
            content += f"\n<!-- {dna} -->\n"
        else:
            content += f"\n# {dna}\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        stamped.append(rel)
        print("盖章:", rel, "→", dna[:60])
    print(f"共盖章 {len(stamped)} · 已有标记跳过 {len(skipped)}")

    # SHA256SUMS 清单（头部 DNA 注释行，sha256sum -c 会跳过非哈希行）
    lines = []
    for path in sorted(iter_files()):
        rel = os.path.relpath(path, ROOT)
        import hashlib
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        lines.append(f"{digest}  {rel}")
    sums_path = os.path.join(ROOT, "SHA256SUMS.sha256")
    header = gen_dna_line("SHA256SUMS.sha256", "文档")
    with open(sums_path, "w", encoding="utf-8") as f:
        f.write(f"# {header}\n")
        f.write("# GADIC-PROV-MVP-001 文件 SHA-256 清单（校验: sha256sum -c SHA256SUMS.sha256）\n")
        f.write("\n".join(lines) + "\n")
    print("SHA256SUMS.sha256 已生成:", len(lines), "个文件")


if __name__ == "__main__":
    main()
