"""ETF 펀드 품질 지표 — 개별주 펀더멘털(fundamentals.py)의 자리를 대신한다

원본 SEPA는 40점을 펀더멘털(매출·EPS·재고)에 배정한다. ETF에는 그 개념이
없다. 대신 "이 상품을 실제로 보유·매매해도 되는가"를 같은 40점으로 본다.

    순자산 규모 15 · 유동성(거래대금) 15 · NAV 괴리율 10

원본이 펀더멘털에서 묻는 것 — 껍데기가 아니라 실체가 받쳐 주는가 — 과 같은
질문을 ETF 언어로 옮긴 것이다. 규모가 작으면 상장폐지·괴리 위험이 있고,
거래대금이 없으면 호가 스프레드가 수익을 먹고, 괴리율이 크면 기초지수가
아니라 프리미엄을 사는 셈이 된다.

원본의 중립 배점 방식을 그대로 쓰고 싶으면 config.FUND_QUALITY_MODE = "neutral".
"""

import logging
import math
from typing import Dict, Optional

log = logging.getLogger(__name__)

# 로그 스케일 앵커 — (하한값 → 0점, 상한값 → 만점)
AUM_ANCHOR = (100.0, 10_000.0)        # 억원: 100억 → 0점, 1조 → 15점
TURNOVER_ANCHOR = (1.0, 100.0)        # 억원/일: 1억 → 0점, 100억 → 15점
PREMIUM_ZERO_AT = 1.0                 # 괴리율 절대값 1% 이상이면 0점


def _log_scale(value: Optional[float], low: float, high: float,
               max_points: float) -> float:
    """로그 구간 선형 환산. value<=low → 0점, value>=high → 만점."""
    if value is None or value <= 0:
        return 0.0
    lo, hi = math.log10(low), math.log10(high)
    pos = (math.log10(value) - lo) / (hi - lo)
    return max(0.0, min(1.0, pos)) * max_points


def build_quality(row: Dict, turnover_eok: float) -> Dict:
    """유니버스 행 + 실측 거래대금 → 채점용 지표 dict.

    Args:
        row: get_etf_list()가 만든 한 행 (code/name/aum_eok/premium_pct 등)
        turnover_eok: 20일 평균 거래대금 (억원) — 주가 데이터에서 실측한 값
    """
    return {
        "code": row.get("code"),
        "aum_eok": _as_float(row.get("aum_eok")),
        "turnover_eok": float(turnover_eok) if turnover_eok is not None else None,
        "turnover_eok_today": _as_float(row.get("turnover_eok")),
        "premium_pct": _as_float(row.get("premium_pct")),
        "nav": _as_float(row.get("nav")),
        "category": row.get("category"),
    }


def _as_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def score_fund_quality(quality: Optional[Dict], reasons: list) -> float:
    """펀드 품질 점수 (40점) — 순자산 15 · 유동성 15 · 괴리율 10."""
    if not quality:
        reasons.append("펀드 정보 없음 (중립 배점)")
        return 20.0

    score = 0.0

    # A) 순자산 규모 (15점)
    aum = quality.get("aum_eok")
    aum_score = _log_scale(aum, *AUM_ANCHOR, 15.0)
    score += aum_score
    if aum is None:
        reasons.append("🔴 순자산 데이터 없음")
    elif aum >= 10_000:
        reasons.append(f"🟢 순자산 {aum/10_000:.1f}조원 (대형 · 청산 위험 낮음)")
    elif aum >= 1_000:
        reasons.append(f"🟢 순자산 {aum:,.0f}억원")
    elif aum >= 300:
        reasons.append(f"🟡 순자산 {aum:,.0f}억원 (중소형)")
    else:
        reasons.append(f"🔴 순자산 {aum:,.0f}억원 (소형 — 상장폐지 요건 근접 주의)")

    # B) 유동성 (15점) — 20일 평균 거래대금
    turnover = quality.get("turnover_eok")
    score += _log_scale(turnover, *TURNOVER_ANCHOR, 15.0)
    if turnover is None:
        reasons.append("🔴 거래대금 데이터 없음")
    elif turnover >= 100:
        reasons.append(f"🟢 거래대금 20일 평균 {turnover:,.0f}억/일 (호가 두터움)")
    elif turnover >= 10:
        reasons.append(f"🟢 거래대금 20일 평균 {turnover:,.1f}억/일")
    elif turnover >= 3:
        reasons.append(f"🟡 거래대금 20일 평균 {turnover:,.1f}억/일 (스프레드 주의)")
    else:
        reasons.append(f"🔴 거래대금 20일 평균 {turnover:,.1f}억/일 (체결 불리)")

    # C) NAV 괴리율 (10점) — 절대값 기준. 1% 이상 벌어지면 0점
    premium = quality.get("premium_pct")
    if premium is None:
        score += 5.0   # 데이터 없으면 중립
        reasons.append("괴리율 데이터 없음 (중립 배점)")
    else:
        gap = abs(premium)
        score += max(0.0, min(10.0, 10.0 - gap / PREMIUM_ZERO_AT * 10.0))
        if gap <= 0.2:
            reasons.append(f"✓ NAV 괴리율 {premium:+.2f}% (정상)")
        elif gap <= 0.5:
            reasons.append(f"🟡 NAV 괴리율 {premium:+.2f}%")
        elif premium > 0:
            reasons.append(f"⚠ NAV 괴리율 {premium:+.2f}% (고평가 거래 — 프리미엄 지불)")
        else:
            reasons.append(f"⚠ NAV 괴리율 {premium:+.2f}% (저평가 거래)")

    return max(0.0, min(score, 40.0))


COMPONENT_BREAKDOWN = [
    ("순자산 규모", 15, "100억 → 0점, 1조 → 15점 (로그 환산)"),
    ("유동성", 15, "20일 평균 거래대금 1억 → 0점, 100억 → 15점 (로그 환산)"),
    ("NAV 괴리율", 10, "괴리 0% → 10점, ±1% 이상 → 0점"),
]
