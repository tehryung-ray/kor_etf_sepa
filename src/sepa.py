"""SEPA 진단 스코어러 (게이트 없음) — 국내 ETF판

원본(snp_sepa_mmt/src/sepa.py)과 배점 체계·판정 로직이 동일하다. 원본이
`stock-screener-main`의 `score_buy_signal()`에서 조기 반환(Phase 2가 아니거나
Trend Template 미달이면 즉시 0점)을 걷어낸 것처럼, 이 모듈도 어떤 국면에 있든
점수 내역을 전부 보여 주고 매수 적격 여부만 `is_buy` / `blocked_reason`으로
따로 표시한다.

배점 (125점 만점):
    추세 구조 40 · 펀드 품질 40 · 손익비 15 · 상대강도 10 · 거래량 10 · 진입 5 · VCP 5

원본과 다른 곳은 40점짜리 한 칸뿐이다. 개별주의 펀더멘털(매출·EPS·재고)은
ETF에 존재하지 않으므로 같은 배점을 펀드 품질(순자산·유동성·괴리율)로 옮겼다.
근거는 `etf_quality.py` 참고. 원본의 중립 배점을 그대로 쓰려면
config.FUND_QUALITY_MODE = "neutral".
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .etf_quality import score_fund_quality
from .phase_indicators import (
    calculate_sma,
    calculate_rs_slope,
    detect_breakout,
    validate_minervini_trend_template,
)

log = logging.getLogger(__name__)


# 8개 Trend Template 조건의 한글 라벨 (표시용) — 원본과 동일
CRITERIA_LABELS = [
    ("price_above_150_200", "주가 > 150일선 · 200일선"),
    ("sma_150_above_200", "150일선 > 200일선"),
    ("sma_200_rising", "200일선 1개월 이상 상승"),
    ("sma_50_above_150", "50일선 > 150일선"),
    ("price_above_50", "주가 > 50일선"),
    ("price_30pct_above_52w_low", "52주 저가 대비 +30% 이상"),
    ("price_near_52w_high", "52주 고가 대비 -25% 이내"),
    ("confirmed_stage_2", "Phase 2 (확정 상승추세)"),
]


def _score_trend(phase: int, phase_info: Dict, price_data: pd.DataFrame,
                 current_price: float, vcp_data: Optional[Dict],
                 reasons: list) -> tuple:
    """추세 구조 점수 (40점) — 이격도·기울기·돌파·과열 페널티."""
    distance_50 = phase_info.get("distance_from_50sma", 0)
    distance_200 = phase_info.get("distance_from_200sma", 0)
    slope_50 = phase_info.get("slope_50", 0)
    slope_200 = phase_info.get("slope_200", 0)

    trend_score = 0.0

    # A) 이동평균 위 이격도 (15점) — 음수 이격은 0점으로 클램프
    distance_component = min(15, max(0,
        (distance_50 / 15.0 * 10) + (distance_200 / 20.0 * 5)
    ))
    trend_score += distance_component

    if distance_50 >= 10:
        reasons.append(f"강한 상승추세: 50일선 +{distance_50:.1f}%")
    elif distance_50 >= 3:
        reasons.append(f"양호한 상승추세: 50일선 +{distance_50:.1f}%")
    elif distance_50 >= 0:
        reasons.append(f"약한 상승추세: 50일선 +{distance_50:.1f}%")
    else:
        reasons.append(f"⚠ 50일선 이탈: {distance_50:.1f}%")

    # B) 이동평균 기울기 (15점)
    slope_component = min(15, max(0,
        (slope_50 / 0.08 * 10) + (slope_200 / 0.05 * 5)
    ))
    trend_score += slope_component

    if slope_50 > 0.05:
        reasons.append(f"이평선 강한 상승 (50:{slope_50:.3f} / 200:{slope_200:.3f})")
    elif slope_50 > 0.02:
        reasons.append("이평선 완만한 상승")
    elif slope_50 > 0:
        reasons.append("이평선 미약한 상승")
    else:
        reasons.append("⚠ 이평선 횡보 또는 하락")

    # C) 돌파 (10점)
    breakout_info = detect_breakout(price_data, current_price, phase_info, vcp_data)
    if breakout_info["is_breakout"]:
        trend_score += 10
        btype = breakout_info["breakout_type"]
        if breakout_info.get("volume_confirmed"):
            reasons.append(f"🟢 {btype} (거래량 확인)")
        else:
            reasons.append(f"🟡 {btype} (거래량 미확인)")

    # D) 과열 페널티 (최대 -10점)
    if distance_50 > 30:
        trend_score -= 10
        reasons.append(f"⚠ 과열: 50일선 +{distance_50:.1f}%")
    elif distance_50 > 20:
        trend_score -= 5
        reasons.append(f"다소 과열: 50일선 +{distance_50:.1f}%")

    return max(0.0, min(trend_score, 40.0)), breakout_info


def _score_volume(price_data: pd.DataFrame, reasons: list) -> float:
    """거래량 점수 (10점) — 상승일 거래량 / 하락일 거래량 비율."""
    if "Volume" not in price_data.columns or len(price_data) < 30:
        return 5.0

    recent_prices = price_data["Close"].iloc[-6:]
    recent_volume = price_data["Volume"].iloc[-5:]

    up_days = down_days = 0
    vol_up = vol_down = 0.0

    for i in range(1, len(recent_prices)):
        change = recent_prices.iloc[i] - recent_prices.iloc[i - 1]
        vol = recent_volume.iloc[i - 1]
        if change > 0:
            up_days += 1
            vol_up += vol
        else:
            down_days += 1
            vol_down += vol

    avg_up = vol_up / up_days if up_days else 0
    avg_down = vol_down / down_days if down_days else 0
    ratio = (avg_up / avg_down) if avg_down > 0 else 1.0

    score = min(10, max(0, 5 + (ratio - 1.0) * 10))

    if ratio >= 1.3:
        reasons.append(f"✓ 상승일 거래량 우위 (비율 {ratio:.2f})")
    elif ratio >= 1.1:
        reasons.append(f"상승일 거래량 소폭 우위 (비율 {ratio:.2f})")
    elif ratio >= 0.9:
        reasons.append(f"거래량 중립 (비율 {ratio:.2f})")
    else:
        reasons.append(f"⚠ 하락일 거래량 우위 (비율 {ratio:.2f} — 분산 매도)")

    return score


def _score_rs(rs_series: pd.Series, reasons: list, benchmark_label: str) -> tuple:
    """상대강도 점수 (10점) — 벤치마크 대비 20일 RS 기울기."""
    if rs_series is None or len(rs_series) < 20 or rs_series.isna().all():
        return 5.0, None

    rs_slope = calculate_rs_slope(rs_series, 20)
    score = min(10, max(0, 5 + (rs_slope * 16.67)))

    if rs_slope > 0.10:
        reasons.append(f"✓ 강한 상대강도: {rs_slope:.3f} ({benchmark_label} 대비 초과수익)")
    elif rs_slope > 0.03:
        reasons.append(f"양(+)의 상대강도: {rs_slope:.3f}")
    elif rs_slope > -0.03:
        reasons.append(f"중립 상대강도: {rs_slope:.3f}")
    elif rs_slope > -0.10:
        reasons.append(f"약한 상대강도: {rs_slope:.3f}")
    else:
        reasons.append(f"⚠ 상대강도 하락: {rs_slope:.3f} ({benchmark_label} 대비 부진)")

    return score, round(rs_slope, 3)


def calculate_atr(price_data: pd.DataFrame, period: int = 14) -> float:
    """Average True Range — 그 종목이 하루에 실제로 움직이는 폭.

    갭(전일 종가 대비 시가 차이)까지 포함하므로 단순 고가-저가보다 실제
    변동폭을 잘 나타낸다.
    """
    if len(price_data) < period + 1:
        return 0.0
    high, low = price_data["High"], price_data["Low"]
    prev_close = price_data["Close"].shift(1)
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else 0.0


def calculate_stop_loss(price_data: pd.DataFrame, current_price: float,
                        phase_info: Dict, phase: int,
                        stop_mode: str = "swing", atr_period: int = 14,
                        atr_mult: float = 3.0,
                        atr_min: float = 0.05, atr_max: float = 0.20) -> float:
    """논리적 손절가 산출.

    stop_mode="swing" — 원본 로직 그대로.
        Phase 2: 최근 10일 저가 또는 50일선 중 높은 쪽 (타이트한 손절)
        그 외  : 최근 30일 베이스 저점
        공통   : 위험폭 3~10% 범위로 강제
    stop_mode="atr"   — ATR × 배수. 위험폭은 atr_min~atr_max 범위로 강제.
        원본의 3~10%는 개별 성장주 기준이라 ETF에는 좁다. 백테스트에서
        손절 거래의 71%가 6개월 안에 매수가를 회복했다.
    """
    if stop_mode == "atr":
        atr = calculate_atr(price_data, atr_period)
        if atr > 0:
            stop = current_price - atr_mult * atr
            risk = (current_price - stop) / current_price
            if risk < atr_min:
                stop = current_price * (1 - atr_min)
            elif risk > atr_max:
                stop = current_price * (1 - atr_max)
            return stop
        # ATR을 못 구하면 원본 방식으로 되돌아간다

    sma_50 = phase_info.get("sma_50", 0)

    if phase == 2:
        recent_low = price_data["Low"].iloc[-10:].min() if len(price_data) >= 10 \
            else price_data["Low"].min()
        swing_stop = recent_low * 0.995
        sma_stop = sma_50 * 0.99 if sma_50 > 0 else swing_stop
        stop = max(swing_stop, sma_stop)

        risk = (current_price - stop) / current_price
        if risk < 0.03:
            stop = current_price * 0.97
        elif risk > 0.10:
            stop = current_price * 0.90
    else:
        base_low = price_data["Low"].iloc[-30:].min() if len(price_data) >= 30 \
            else price_data["Low"].min()
        stop = base_low * 0.99
        if (current_price - stop) / current_price > 0.10:
            stop = current_price * 0.90

    return stop


def _score_risk_reward(current_price: float, stop_loss: float, phase: int,
                       phase_info: Dict, breakout_info: Dict,
                       reasons: list) -> tuple:
    """손익비 점수 (15점) — 2:1 미만은 0점, 5:1 이상 만점."""
    risk = current_price - stop_loss

    if phase == 2:
        target = current_price * 1.30
    elif breakout_info.get("is_breakout"):
        target = breakout_info["breakout_level"] * 1.25
    else:
        sma_50 = phase_info.get("sma_50", 0)
        target = sma_50 * 1.25 if sma_50 > 0 else current_price * 1.25

    reward = target - current_price

    if risk <= 0 or reward <= 0:
        return 0.0, 0.0, target, risk

    rr = reward / risk
    score = 0.0 if rr < 2.0 else min(15, ((rr - 2.0) * 6) + 3)

    if rr >= 5.0:
        reasons.append(f"🟢 탁월한 손익비: {rr:.1f}:1 (상승 {reward:,.0f}원 / 위험 {risk:,.0f}원)")
    elif rr >= 4.0:
        reasons.append(f"🟢 우수한 손익비: {rr:.1f}:1")
    elif rr >= 3.0:
        reasons.append(f"🟢 양호한 손익비: {rr:.1f}:1")
    elif rr >= 2.0:
        reasons.append(f"🟡 수용 가능한 손익비: {rr:.1f}:1")
    else:
        reasons.append(f"🔴 부족한 손익비: {rr:.1f}:1 (최소 2:1 필요)")

    return score, round(rr, 2), target, risk


def _score_entry(phase: int, phase_info: Dict, current_price: float,
                 reasons: list) -> tuple:
    """진입 품질 점수 (5점) — 미너비니 피벗 포인트 방법론.

    Phase 2·3(주도 국면): 52주 고가 근접도 3점 + 50일선 이격 2점
    Phase 1·4(베이스 국면): 50일선 돌파 지점 근접도 5점 환산
    """
    week_52_high = phase_info.get("week_52_high", current_price)
    distance_50 = phase_info.get("distance_from_50sma", 0)
    gap_52w = ((current_price - week_52_high) / week_52_high * 100) if week_52_high > 0 else -100

    entry_score = 0.0

    if phase in (2, 3):
        # 52주 고가 근접도 (3점)
        if gap_52w >= -5:
            entry_score += 3
            reasons.append(f"🟢 52주 고가권: 고가 대비 {abs(gap_52w):.1f}% (피벗 존)")
        elif gap_52w >= -15:
            entry_score += 3 - ((abs(gap_52w) - 5) / 10.0)
            reasons.append(f"🟢 52주 고가 근접: 고가 대비 {abs(gap_52w):.1f}%")
        elif gap_52w >= -25:
            entry_score += 2 - ((abs(gap_52w) - 15) / 10.0)
            reasons.append(f"🟡 52주 고가 25% 이내: 고가 대비 {abs(gap_52w):.1f}%")
        else:
            reasons.append(f"🔴 52주 고가에서 이탈: 고가 대비 {abs(gap_52w):.1f}% (주도 상품 아님)")

        # 50일선 이격 (2점)
        if 0 < distance_50 <= 20:
            entry_score += 2 - (distance_50 / 20.0)
        elif distance_50 > 20:
            entry_score += max(0, 1 - ((distance_50 - 20) / 15.0))
    else:
        # 돌파 지점(50일선 +1%) 근접도
        deviation = abs(distance_50 - 1.0)
        entry_score += max(0, 2 - (deviation / 6.0) * 2)

        if -1 <= distance_50 <= 3:
            reasons.append(f"✓ 최적 돌파 구간: 50일선 {distance_50:.1f}%")
        elif -4 <= distance_50 <= 6:
            reasons.append(f"양호한 진입 구간: 50일선 {distance_50:.1f}%")
        else:
            reasons.append(f"진입 구간 이탈: 50일선 {distance_50:.1f}%")

    return min(5.0, max(0.0, entry_score)), round(gap_52w, 1)


def _score_vcp(vcp_data: Optional[Dict], reasons: list) -> float:
    """VCP 보너스 (5점) — 변동성 수축 패턴 품질에 따라 1/3/5점."""
    if not vcp_data or not vcp_data.get("is_vcp"):
        if vcp_data and vcp_data.get("contraction_count", 0) > 0:
            reasons.append(f"🟡 부분 패턴: {vcp_data.get('pattern_details', '')}")
        return 0.0

    quality = vcp_data.get("vcp_quality", 0)
    detail = vcp_data.get("pattern_details", "")

    if quality >= 80:
        reasons.append(f"⭐ VCP 패턴: {detail} (품질 {quality:.0f}/100)")
        return 5.0
    if quality >= 60:
        reasons.append(f"🟢 VCP 패턴: {detail} (품질 {quality:.0f}/100)")
        return 3.0
    reasons.append(f"🟡 VCP 패턴: {detail} (품질 {quality:.0f}/100)")
    return 1.0


def score_sepa(code: str,
               price_data: pd.DataFrame,
               current_price: float,
               phase_info: Dict,
               rs_series: pd.Series,
               quality: Optional[Dict] = None,
               vcp_data: Optional[Dict] = None,
               template_pass_min: int = 7,
               buy_threshold: int = 60,
               fund_quality_mode: str = "etf",
               benchmark_label: str = "KOSPI",
               stop_mode: str = "swing", atr_period: int = 14,
               atr_mult: float = 3.0, atr_min: float = 0.05,
               atr_max: float = 0.20,
               require_52w_low: bool = False) -> Dict:
    """SEPA 종합 점수를 계산한다. Phase에 관계없이 항상 전 항목을 채점한다.

    Returns:
        점수 내역 · Trend Template 8개 조건 · 손절/익절가 · 매수 적격 여부
    """
    phase = phase_info.get("phase", 0)
    reasons: list = []

    # Minervini Trend Template (8개 조건) — 순수 SEPA 점수
    sma_200_series = calculate_sma(price_data["Close"], 200)
    template = validate_minervini_trend_template(current_price, phase_info, sma_200_series)

    # 각 항목 채점
    trend_score, breakout_info = _score_trend(
        phase, phase_info, price_data, current_price, vcp_data, reasons)

    if fund_quality_mode == "neutral":
        fund_score = 20.0
        reasons.append("펀드 품질: 중립 배점 (neutral 모드)")
    else:
        fund_score = score_fund_quality(quality, reasons)

    volume_score = _score_volume(price_data, reasons)
    rs_score, rs_slope = _score_rs(rs_series, reasons, benchmark_label)

    stop_loss = calculate_stop_loss(price_data, current_price, phase_info, phase,
                                    stop_mode=stop_mode, atr_period=atr_period,
                                    atr_mult=atr_mult, atr_min=atr_min, atr_max=atr_max)
    rr_score, rr_ratio, target, risk = _score_risk_reward(
        current_price, stop_loss, phase, phase_info, breakout_info, reasons)

    entry_score, gap_52w = _score_entry(phase, phase_info, current_price, reasons)
    vcp_score = _score_vcp(vcp_data, reasons)

    total = (trend_score + fund_score + volume_score + rs_score
             + rr_score + entry_score + vcp_score)
    total = max(0.0, min(total, 125.0))

    # 매수 적격 판정 — 원본 게이트를 여기서만 적용
    passes_template = template["criteria_passed"] >= template_pass_min
    # ③ 8개 중 유일하게 "실제로 움직이는가"를 묻는 조건. 7/8 기준에서는 이것만
    #    빠져도 통과하므로, 저변동 상품을 걸러내려면 따로 필수로 둬야 한다.
    moves_enough = bool(template["criteria_details"].get("price_30pct_above_52w_low"))

    blocked = None
    if phase != 2:
        blocked = f"Phase {phase} (미너비니는 Phase 2만 매수)"
    elif not passes_template:
        blocked = f"Trend Template {template['criteria_passed']}/8 (최소 {template_pass_min} 필요)"
    elif require_52w_low and not moves_enough:
        blocked = "52주 저가 대비 +30% 미달 (저변동 상품 배제)"
    elif total < buy_threshold:
        blocked = f"SEPA {total:.0f}점 (임계값 {buy_threshold} 미달)"

    # 1차 익절가 = (현재가 + 익절가) ÷ 2 — 절반 익절 후 손절가를 매수가로 이동
    mid_target = (current_price + target) / 2 if target > current_price else None

    return {
        "code": code,
        "phase": phase,
        "phase_name": phase_info.get("phase_name", ""),
        "phase_confidence": phase_info.get("confidence", 0),
        "sepa_score": round(total, 1),
        "is_buy": blocked is None,
        "blocked_reason": blocked,
        "template_score": template["template_score"],
        "criteria_passed": template["criteria_passed"],
        "criteria_details": template["criteria_details"],
        "passes_template": passes_template,
        "components": {
            "trend": round(trend_score, 1),
            "fund_quality": round(fund_score, 1),
            "risk_reward": round(rr_score, 1),
            "relative_strength": round(rs_score, 1),
            "volume": round(volume_score, 1),
            "entry": round(entry_score, 1),
            "vcp": round(vcp_score, 1),
        },
        "current_price": round(current_price),
        "stop_loss": round(stop_loss),
        "target": round(target),
        "mid_target": round(mid_target) if mid_target else None,
        "risk_amount": round(risk),
        "stop_mode": stop_mode,
        "risk_pct": round((current_price - stop_loss) / current_price * 100, 2),
        "risk_reward_ratio": rr_ratio,
        "rs_slope": rs_slope,
        "gap_from_52w_high": gap_52w,
        "sma_50": phase_info.get("sma_50"),
        "sma_200": phase_info.get("sma_200"),
        "aum_eok": (quality or {}).get("aum_eok"),
        "turnover_eok": (quality or {}).get("turnover_eok"),
        "premium_pct": (quality or {}).get("premium_pct"),
        "vcp_quality": vcp_data.get("vcp_quality") if vcp_data else None,
        "is_vcp": bool(vcp_data and vcp_data.get("is_vcp")),
        "breakout": breakout_info.get("breakout_type") if breakout_info.get("is_breakout") else None,
        "reasons": reasons,
    }


# 컴포넌트 만점 (표시용)
COMPONENT_MAX = {
    "trend": 40,
    "fund_quality": 40,
    "risk_reward": 15,
    "relative_strength": 10,
    "volume": 10,
    "entry": 5,
    "vcp": 5,
}

COMPONENT_LABELS = {
    "trend": "추세 구조",
    "fund_quality": "펀드 품질",
    "risk_reward": "손익비",
    "relative_strength": "상대강도",
    "volume": "거래량",
    "entry": "진입 품질",
    "vcp": "VCP",
}
