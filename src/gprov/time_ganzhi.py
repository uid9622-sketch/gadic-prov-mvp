"""干支纪时桥接（2026-11-14 合并令：天干地支引擎 × 溯源证据链）。

双层设计（2026-11-14 开源适配）：
- 第一层（本机优先）：复用真身 longhun-system/08_BIN/lh_time_engine.py，不复制不造轮；
- 第二层（内嵌兜底）：真身缺席时（CI/第三方环境）使用本文件内嵌的公历→干支换算，
  公式与真身对照校准（年柱=公历年年干支；日柱=2000-01-01 戊午锚点推进；
  月柱=近似节气日 + 五虎遁；时支=(h+1)//2）。
- 两层都失败才返回 None，**不编造**（与规范 §0.3 反误报铁律同款）。

诚实边界（写死）：
- ganzhi_stamp 由本机时钟推出，属文化纪时辅助字段 = SELF_ASSERTED；
- 它不是可信时间，不替代 RFC 3161 TST，不参与任何密码学绑定；
- 证据链的可信时间唯一来源仍是 M3（当前 NOT_CONFIGURED）；
- 内嵌兜底的月柱节气边界采用近似日（每年真实节气 ±1 天浮动），
  节气边界当天出生的月柱可能差一位——对齐天文精度请使用第一层真身引擎。

Schema 说明：log-event 增加可选字段 `ganzhi_stamp`（可空），加性变更不破坏 §5.4；
语义已定义（本字段），符合规范 §5.6 可选字段规则。
"""
import sys
from datetime import date, datetime, timedelta
from typing import Optional

_LH_BIN = "/Users/zuimeidedeyihan/longhun-system/08_BIN"

_GAN = "甲乙丙丁戊己庚辛壬癸"
_ZHI = "子丑寅卯辰巳午未申酉戌亥"

# 各月"节"的近似公历日（立春/惊蛰/清明/立夏/芒种/小暑/立秋/白露/寒露/立冬/大雪/小寒）
_APPROX_JIE = [(2, 4), (3, 6), (4, 5), (5, 6), (6, 6), (7, 7),
               (8, 8), (9, 8), (10, 8), (11, 7), (12, 7), (1, 6)]

# 五虎遁：年干序 → 正月（寅）天干序
_WUHU = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}

_DAY_ANCHOR = (54, date(2000, 1, 1))  # 2000-01-01 = 戊午（序 54）


def _load_engine():
    """懒加载干支引擎；失败返回 None（不编造）。"""
    try:
        if _LH_BIN not in sys.path:
            sys.path.insert(0, _LH_BIN)
        from lh_time_engine import 当前四柱  # noqa
        return 当前四柱
    except Exception:
        return None


def _year_pillar(dt: datetime) -> str:
    """年柱：公历年年干支（与真身引擎同规则，非立春切换）。"""
    n = (dt.year - 1984) % 60
    return _GAN[n % 10] + _ZHI[n % 12]


def _day_pillar(dt: datetime) -> str:
    """日柱：锚点推进法。"""
    anchor_n, anchor_d = _DAY_ANCHOR
    n = (anchor_n + (dt.date() - anchor_d).days) % 60
    return _GAN[n % 10] + _ZHI[n % 12]


def _month_pillar(dt: datetime) -> str:
    """月柱：近似节气定月支 + 五虎遁定月干。

    节气序列：立春起寅月（序 0），逐月顺排至小寒丑月（序 11）。
    """
    y = dt.year
    # 生成本年的节切换点：立春(寅0)…立冬(亥9) 共 10 个 + 大雪(子10) + 小寒(丑11)
    switches = [(y, m, d, i) for i, (m, d) in enumerate(_APPROX_JIE[:10])]
    switches.append((y, 12, _APPROX_JIE[10][1], 10))      # 本年大雪 → 子月
    switches.append((y, 1, _APPROX_JIE[11][1], 11))       # 本年小寒 → 丑月
    switches.append((y - 1, 12, _APPROX_JIE[10][1], 10))  # 上年大雪（跨年子月）
    switches.append((y - 1, 1, _APPROX_JIE[11][1], 11))   # 上年小寒
    # 找 dt 之前最近的节切换点
    cur = None
    for (yy, mm, dd, idx) in sorted(switches):
        if datetime(yy, mm, dd) <= dt:
            cur = idx
    if cur is None:
        cur = 11  # dt 早于上年小寒（理论不达）
    zhi_idx = (2 + cur) % 12  # 寅=2
    # 年干定正月干，按月支序顺推
    yn = (y - 1984) % 60
    gan_start = _WUHU[yn % 10]
    gan_idx = (gan_start + cur) % 10
    return _GAN[gan_idx] + _ZHI[zhi_idx]


def _hour_label(dt: datetime) -> str:
    """时支 + 时。子时跨 23:00–01:00。"""
    zhi_idx = ((dt.hour + 1) // 2) % 12
    return _ZHI[zhi_idx] + "时"


def _fallback_pillars(ts: Optional[datetime]) -> tuple:
    """内嵌兜底：返回四柱元组（与真身输出同形）。"""
    if ts is None:
        ts = datetime.now()
    return (_year_pillar(ts), _month_pillar(ts), _day_pillar(ts), _hour_label(ts))


def ganzhi_stamp(ts: Optional[datetime] = None) -> Optional[str]:
    """返回 '丙午年·己亥月·壬辰日·卯时' 形式干支四柱；两层全失败返回 None。"""
    fn = _load_engine()
    if fn is not None:
        try:
            pillars = fn(ts)
            # 时辰() 自带"时"字（如"卯时"），只给年月日补后缀
            labels = ("年", "月", "日", "")
            return "·".join(p + l for p, l in zip(pillars, labels))
        except Exception:
            pass  # 真身异常 → 落到内嵌兜底
    try:
        pillars = _fallback_pillars(ts)
        labels = ("年", "月", "日", "")
        return "·".join(p + l for p, l in zip(pillars, labels))
    except Exception:
        return None

# 🧬 #龍芯⚡️丙午·己亥·壬辰·癸卯·䷟恒-代码-创建-8c708adf
