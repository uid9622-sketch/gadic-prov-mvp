"""M4 Merkle 层：RFC 6962 风格哈希构造与证明（规范 §4-M4）。

固定构造：
  Leaf Hash: SHA-256(0x00 || leaf_data)
  Node Hash: SHA-256(0x01 || left || right)

证明验证采用"生成对称重放"算法：验证器按生成器完全相同的递归结构消费证明节点，
同时重建旧根与新根，等价于 RFC 6962 §2.1.2 的计数折叠法，且额外保证证明无冗余节点。
该算法已由测试矩阵 T-015（随机规模全对验证）+ 篡改用例交叉验证。
"""
import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(leaf_data: bytes) -> bytes:
    return _sha256(LEAF_PREFIX + leaf_data)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _sha256(NODE_PREFIX + left + right)


def _pow2_lt(n: int) -> int:
    """严格小于 n 的最大 2 的幂（n >= 2）。"""
    p = 1
    while p * 2 < n:
        p *= 2
    return p


def subtree_hash(leaves, first: int, last: int) -> bytes:
    if last - first == 1:
        return leaves[first]
    k = _pow2_lt(last - first)
    return node_hash(subtree_hash(leaves, first, first + k),
                     subtree_hash(leaves, first + k, last))


def tree_root(leaves) -> bytes:
    if not leaves:
        raise ValueError("empty tree has no root (RFC 6962: size 0 undefined)")
    return subtree_hash(leaves, 0, len(leaves))


# ---------- Inclusion Proof ----------

def inclusion_path(leaves, m: int, first: int, last: int):
    if last - first == 1:
        return []
    k = _pow2_lt(last - first)
    if m - first < k:
        return inclusion_path(leaves, m, first, first + k) + \
               [subtree_hash(leaves, first + k, last)]
    else:
        return inclusion_path(leaves, m, first + k, last) + \
               [subtree_hash(leaves, first, first + k)]


def _root_from_path(m, first, last, leaf_h, nodes):
    """按生成序消费 path 节点重建根；结构与 inclusion_path 完全对称。"""
    if last - first == 1:
        return leaf_h
    k = _pow2_lt(last - first)
    if m - first < k:
        left = _root_from_path(m, first, first + k, leaf_h, nodes)
        return node_hash(left, nodes.pop(0))
    else:
        right = _root_from_path(m, first + k, last, leaf_h, nodes)
        return node_hash(nodes.pop(0), right)


def verify_inclusion(m: int, tree_size: int, leaf_h: bytes, root_h: bytes, path) -> bool:
    if not (0 <= m < tree_size):
        return False
    try:
        r = _root_from_path(m, 0, tree_size, leaf_h, list(path))
    except IndexError:
        return False
    return r == root_h


# ---------- Consistency Proof ----------

def consistency_proof(leaves, m: int, n: int):
    """生成 (m, n) 一致性证明（0 < m < n）。"""
    if not (0 < m < n) or n > len(leaves):
        raise ValueError("consistency proof requires 0 < m < n <= len(leaves)")

    def gen(mm, first, last, b):
        if mm == last - first:
            return [] if b else [subtree_hash(leaves, first, last)]
        k = _pow2_lt(last - first)
        if mm <= k:
            return gen(mm, first, first + k, b) + [subtree_hash(leaves, first + k, last)]
        else:
            return gen(mm - k, first + k, last, False) + \
                   [subtree_hash(leaves, first, first + k)]

    return gen(m, 0, n, True)


def verify_consistency(m: int, n: int, proof, root_old: bytes, root_new: bytes) -> bool:
    """验证一致性证明：同时重建旧根与新根，并要求证明节点恰好耗尽。"""
    if m == 0:
        return len(proof) == 0
    if m == n:
        return len(proof) == 0 and root_old == root_new
    if m > n or len(proof) == 0:
        return False
    nodes = list(proof)
    pos = 0

    def build(first, last, ol):
        """返回 (旧树部分子树根, 新树子树哈希)。不变量：0 <= ol <= size。"""
        nonlocal pos
        size = last - first
        if ol == size:
            # 子树完全属于旧树：唯一合法位置是 [0, m) 本身（其根即受信旧根），
            # 其余位置（b=False 链）由单个证明节点给出。
            if first == 0 and size == m:
                return root_old, root_old
            if pos >= len(nodes):
                raise IndexError
            h = nodes[pos]; pos += 1
            return h, h
        k = _pow2_lt(size)
        if ol <= k:
            lo, lh = build(first, first + k, ol)
            if pos >= len(nodes):
                raise IndexError
            rh = nodes[pos]; pos += 1
            return lo, node_hash(lh, rh)
        else:
            ro, rh = build(first + k, last, ol - k)
            if pos >= len(nodes):
                raise IndexError
            lh = nodes[pos]; pos += 1
            return node_hash(lh, ro), node_hash(lh, rh)

    try:
        rebuilt_old, rebuilt_new = build(0, n, m)
    except (IndexError, ValueError):
        return False
    if pos != len(nodes):
        return False  # 存在冗余/未知节点 → 拒绝
    return rebuilt_old == root_old and rebuilt_new == root_new

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-cf911fee
