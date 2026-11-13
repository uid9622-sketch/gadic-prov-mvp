# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-check_dna-20261114
"""溯源标记检查：src/scripts/tests 下每个 .py 必须带 #龍芯⚡️ 出身证明。

CI 用（跨平台确定性，不依赖 grep 的 locale/emoji 行为）：
    python scripts/check_dna.py
缺章 → 打印文件名并 exit 1；全齐 → 打印统计并 exit 0。
"""
import pathlib
import subprocess
import sys


def main() -> int:
    files = subprocess.run(
        ["git", "ls-files", "src", "scripts", "tests"],
        capture_output=True, text=True,
    ).stdout.split()
    files = [f for f in files if f.endswith(".py") and pathlib.Path(f).exists()]
    missing = [f for f in files if "龍芯" not in pathlib.Path(f).read_text(encoding="utf-8")]
    for f in missing:
        print("缺溯源标记:", f)
    print(f"检查 {len(files)} 个 .py 文件，缺 {len(missing)} 个")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
