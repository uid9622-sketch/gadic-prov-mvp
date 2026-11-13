"""Notion 页面顶层块扫描（查重复标题用）。只读。"""
import json
import subprocess
import sys

sys.path.insert(0, "/Users/zuimeidedeyihan/longhun-system/08_BIN")
from lh_notion令牌 import get_token  # noqa: E402

PAGE = "1977125a9c9f83a796bf01cc8f598577"


def main():
    tok = get_token()
    cursor = None
    all_res = []
    while True:
        url = f"https://api.notion.com/v1/blocks/{PAGE}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        r = subprocess.run(
            ["curl", "-s", "-X", "GET", url,
             "-H", f"Authorization: Bearer {tok}",
             "-H", "Notion-Version: 2022-06-28"],
            capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout)
        res = d.get("results", [])
        all_res.extend(res)
        if not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    print("total_blocks:", len(all_res))
    h2 = []
    for b in all_res:
        t = b["type"]
        if t.startswith("heading"):
            txt = "".join(x.get("plain_text", "") for x in b[t]["rich_text"])
            if t == "heading_2":
                h2.append((b["id"], txt))
            print(b["id"][:10], t, txt[:70])
    print("--- H2 list ---")
    for i, (bid, txt) in enumerate(h2):
        print(i, bid[:10], txt)


if __name__ == "__main__":
    main()

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-3a6fd5f2
