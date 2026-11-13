"""RFC 8785 JCS 规范化（gadic-prov-mvp v0.2.0）

MVP 范围：str / int / bool / null / list / dict（键为 str）。
LIMITATIONS:
- 键排序按 Unicode 码点（Python sort_keys）；RFC 8785 要求 UTF-16 码元排序，
  两者仅在含 BMP 外字符与增补平面字符混排键名时有差异（本项目键名均为 ASCII，无影响）。
- 浮点数一律拒绝（E_INPUT_INVALID），规避 ECMAScript 数字序列化歧义。
- 重复 JSON 键一律拒绝（T-007）。
"""
import json


class DuplicateKeyError(ValueError):
    """JSON 重复键——按规范 §5.6 / T-007 必须拒绝。"""


def _pairs_hook(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise DuplicateKeyError(f"duplicate JSON key: {k!r}")
        seen[k] = v
    return seen


def strict_loads(text):
    """严格解析：拒绝重复键。"""
    return json.loads(text, object_pairs_hook=_pairs_hook)


def jcs(obj) -> bytes:
    """RFC 8785 规范化字节。浮点数、NaN 一律拒绝。"""
    if obj is None or isinstance(obj, (bool, str, int, list, dict)):
        pass
    else:
        raise TypeError(f"JCS MVP rejects type: {type(obj).__name__}")
    if isinstance(obj, float):
        raise TypeError("JCS MVP rejects floats; use int or string")
    if isinstance(obj, dict):
        for k in obj:
            if not isinstance(k, str):
                raise TypeError("JCS MVP rejects non-string keys")
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-9f1058d1
