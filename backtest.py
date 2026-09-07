"""과거 데이터 백테스트 — 이 스크리너의 규칙을 그대로 과거에 적용한다

규칙은 run_daily.py와 동일한 코드(src/momentum, src/phase_indicators, src/sepa)를
쓴다. 백테스트용으로 따로 만든 지표는 하나도 없다.

  진입  신호일(T) 종가 기준으로 3관문(Phase 2 · 템플릿 N/8 · SEPA 임계값) 통과 →
        다음 거래일(T+1) 시가에 매수. 스캔이 장 마감 후 돌기 때문에 당일 매수는
        불가능하다.
  청산  ① 손절가 도달 → 전량   ② 1차 익절 도달 → 절반 + 손절가를 매수가로
        ③ 최종 익절 도달 → 나머지.  가격은 진입 시점 값으로 고정한다.
  수량  (자본 × 종목당 감수비율) ÷ (매수가 − 손절가). 종목당 최대 비중 상한 적용.

── 반드시 알아야 할 한계 ───────────────────────────────────────────────
1. 생존편향. 유니버스가 '오늘 상장되어 있는' ETF 목록이다. 그 사이 상장폐지된
   ETF는 애초에 목록에 없다. 실패한 상품이 통째로 빠져 있으므로 결과는
   실제보다 좋게 나온다. 이 편향은 제거할 방법이 없다.
2. 유니버스 확대. 국내 ETF는 최근 몇 년 사이 폭발적으로 늘었다. 2019년 시점의
   후보는 200여 개뿐이고 그마저 지금까지 살아남은 것들이다.
3. 펀드 품질 40점은 과거 재구성이 불가능하다(과거 시점의 순자산·NAV 데이터가
   없다). 기본값은 'neutral'(전 종목 20점 고정)로 돌린다. 오늘 순자산을 쓰는
   'etf' 모드는 미래 정보를 쓰는 것이라 참고용 민감도 분석으로만 본다.
4. 체결 가정. 시가/지정가에 슬리피지 없이 체결된다고 본다. 실제로는 호가
   스프레드와 미체결이 있다. 수수료는 왕복으로 반영한다.
"""

import argparse
import json
import logging
import math
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import config
from src.momentum import calc_momentum_score
from src.phase_indicators import (
    classify_phase, calculate_relative_strength, detect_vcp_pattern,
)
from src.sepa import score_sepa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")


# ── 데이터 ────────────────────────────────────────────────────────────
def load_cache(path: str) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def build_matrices(prices: dict):
    """종가·거래대금 매트릭스와 코드별 인덱스 배열을 만든다."""
    close = pd.DataFrame({c: d["Close"] for c, d in prices.items()}).sort_index()
    turnover = pd.DataFrame({
        c: (d["Close"] * d["Volume"]).rolling(20).mean() / 1e8   # 억원
        for c, d in prices.items()
    }).sort_index()
    idx_vals = {c: d.index.values for c, d in prices.items()}
    return close, turnover, idx_vals


# ── 포지션 ────────────────────────────────────────────────────────────
class Position:
    __slots__ = ("code", "name", "category", "entry_date", "entry", "stop",
                 "mid", "target", "shares", "init_shares", "half_done",
                 "sepa", "momentum", "realized", "fees")

    def __init__(self, code, name, category, entry_date, entry, stop, mid,
                 target, shares, sepa, momentum):
        self.code, self.name, self.category = code, name, category
        self.entry_date, self.entry = entry_date, entry
        self.stop, self.mid, self.target = stop, mid, target
        self.shares = self.init_shares = shares
        self.half_done = False
        self.sepa, self.momentum = sepa, momentum
        self.realized = 0.0
        self.fees = 0.0


def run(data: dict, start: str, end: str, top_n: int, fund_mode: str,
        risk_pct: float, max_positions: int, max_weight: float,
        fee_bp: float, initial: float, min_turnover: float,
        require_c6: bool = False) -> dict:

    prices, bm, meta = data["prices"], data["bm"], data["meta"]
    close, turnover, idx_vals = build_matrices(prices)

    # 벤치마크 정렬
    bm_close = bm["Close"]
    if bm_close.index.tz is not None:
        bm_close.index = bm_close.index.tz_localize(None)

    mom = calc_momentum_score(close, config.MOMENTUM_WEIGHTS, config.SKIP_RECENT_MONTH)

    cal = close.index
    t0 = cal.searchsorted(pd.Timestamp(start))
    t1 = cal.searchsorted(pd.Timestamp(end), side="right")
    days = cal[t0:t1]
    log.info("백테스트 구간 %s ~ %s (%d거래일), 유니버스 후보 %d종목",
             days[0].date(), days[-1].date(), len(days), close.shape[1])

    fee = fee_bp / 10000.0
    cash = initial
    positions: dict = {}
    trades: list = []
    equity_curve: list = []
    daily_eligible: list = []
    skipped_no_slot = skipped_no_cash = 0

    pending: list = []          # 전일 신호 → 오늘 시가 매수 대기

    for di, today in enumerate(days):
        # ── 1) 보유 포지션 청산 점검 (오늘 OHLC) ─────────────────────
        for code in list(positions):
            p = positions[code]
            df = prices[code]
            k = np.searchsorted(idx_vals[code], today.to_datetime64(), side="right")
            if k == 0 or idx_vals[code][k - 1] != today.to_datetime64():
                continue                                  # 오늘 거래 없음
            bar = df.iloc[k - 1]
            o, h, l = float(bar["Open"]), float(bar["High"]), float(bar["Low"])

            # 손절 우선(보수적). 시가가 이미 손절가 아래면 시가 체결.
            if l <= p.stop:
                px = min(o, p.stop) if o <= p.stop else p.stop
                proceeds = p.shares * px * (1 - fee)
                cash += proceeds
                p.realized += proceeds
                kind = "부분익절+본전청산" if p.half_done else "손절"
                trades.append(_close_trade(p, today, px, kind))
                del positions[code]
                continue

            # 1차 익절
            if not p.half_done and h >= p.mid:
                half = p.shares // 2
                if half > 0:
                    proceeds = half * p.mid * (1 - fee)
                    cash += proceeds
                    p.realized += proceeds
                    p.shares -= half
                p.half_done = True
                p.stop = p.entry                          # 손절가를 매수가로
            # 최종 익절
            if h >= p.target and p.shares > 0:
                proceeds = p.shares * p.target * (1 - fee)
                cash += proceeds
                p.realized += proceeds
                trades.append(_close_trade(p, today, p.target, "익절"))
                del positions[code]

        # ── 2) 전일 신호 체결 (오늘 시가) ────────────────────────────
        for sig in pending:
            code = sig["code"]
            if code in positions or len(positions) >= max_positions:
                skipped_no_slot += 1
                continue
            k = np.searchsorted(idx_vals[code], today.to_datetime64(), side="right")
            if k == 0 or idx_vals[code][k - 1] != today.to_datetime64():
                continue
            entry = float(prices[code].iloc[k - 1]["Open"])
            if entry <= 0:
                continue
            # 신호 시점 손절/익절 비율을 시가에 재적용 (가격이 갭이 나도 계획은 비율 유지)
            stop = entry * (sig["stop"] / sig["price"])
            target = entry * (sig["target"] / sig["price"])
            mid = (entry + target) / 2
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                continue

            equity_now = cash + sum(_mtm(p, prices, idx_vals, today) for p in positions.values())
            shares = int((equity_now * risk_pct) // risk_per_share)
            shares = min(shares, int((equity_now * max_weight) // entry))
            cost = shares * entry * (1 + fee)
            if shares <= 0:
                continue
            if cost > cash:
                shares = int(cash // (entry * (1 + fee)))
                cost = shares * entry * (1 + fee)
                if shares <= 0:
                    skipped_no_cash += 1
                    continue
            cash -= cost
            positions[code] = Position(
                code, meta.get(code, {}).get("name", code),
                meta.get(code, {}).get("category", "기타"),
                today, entry, stop, mid, target, shares,
                sig["sepa"], sig["momentum"])
            positions[code].fees = shares * entry * fee
        pending = []

        # ── 3) 오늘 종가 기준 스캔 → 내일 매수 후보 ──────────────────
        mrow = mom.loc[today].dropna()
        trow = turnover.loc[today]
        ok = trow[trow >= min_turnover].index
        mrow = mrow[mrow.index.isin(ok)]
        ranked = mrow.sort_values(ascending=False).head(top_n)

        n_elig = 0
        bm_upto = bm_close.loc[:today]
        for rank, (code, mscore) in enumerate(ranked.items(), 1):
            df = prices[code]
            k = np.searchsorted(idx_vals[code], today.to_datetime64(), side="right")
            if k < 200:
                continue
            sl = df.iloc[:k]
            price = float(sl["Close"].iloc[-1])
            try:
                phase = classify_phase(sl, price)
                if phase.get("phase", 0) == 0:
                    continue
                rs = calculate_relative_strength(sl["Close"], bm_upto)
                vcp = detect_vcp_pattern(sl, price, phase)
                quality = None
                if fund_mode == "etf":
                    # 순자산·괴리율은 과거 값이 없어 '오늘' 값을 쓴다 = 미래 정보.
                    # 거래대금만 해당 시점의 실제 20일 평균을 쓴다.
                    m = meta.get(code, {})
                    quality = {"aum_eok": m.get("aum_eok"),
                               "turnover_eok": float(trow.get(code, 0.0)),
                               "premium_pct": m.get("premium_pct")}
                res = score_sepa(
                    code=code, price_data=sl, current_price=price,
                    phase_info=phase, rs_series=rs, quality=quality, vcp_data=vcp,
                    template_pass_min=config.TEMPLATE_PASS_MIN,
                    buy_threshold=config.SEPA_BUY_THRESHOLD,
                    fund_quality_mode=fund_mode,
                    benchmark_label=config.BENCHMARK_LABEL)
            except Exception:
                continue
            # 저변동 상품(채권·단기금리 ETF) 차단용 옵션.
            # '52주 저가 대비 +30%'는 8개 조건 중 유일하게 "실제로 움직이는가"를
            # 묻는다. 7/8 기준에서는 이것만 빠져도 통과하므로 필수로 둘 수 있게 한다.
            if require_c6 and not res["criteria_details"].get("price_30pct_above_52w_low"):
                continue
            if res["is_buy"]:
                n_elig += 1
                if code not in positions:
                    pending.append({"code": code, "price": price,
                                    "stop": res["stop_loss"], "target": res["target"],
                                    "sepa": res["sepa_score"], "momentum": round(float(mscore), 4)})
        daily_eligible.append(n_elig)

        # ── 4) 자산 기록 ─────────────────────────────────────────────
        mtm = sum(_mtm(p, prices, idx_vals, today) for p in positions.values())
        equity_curve.append({"date": today.strftime("%Y-%m-%d"),
                             "equity": round(cash + mtm, 2),
                             "cash": round(cash, 2),
                             "positions": len(positions)})

        if di % 250 == 0:
            log.info("  %s  자산 %s원  보유 %d  누적거래 %d",
                     today.date(), f"{cash + mtm:,.0f}", len(positions), len(trades))

    # 종료 시점 미청산 포지션은 마지막 종가로 평가만 하고 별도 표기
    last = days[-1]
    open_positions = []
    for code, p in positions.items():
        px = _last_price(p, prices, idx_vals, last)
        cost = p.init_shares * p.entry + p.fees
        value = p.realized + p.shares * px          # 이미 실현한 절반 + 남은 평가액
        open_positions.append({
            "code": code, "name": p.name, "category": p.category,
            "entry_date": p.entry_date.strftime("%Y-%m-%d"),
            "entry": round(p.entry), "last": round(px),
            "shares": p.shares, "init_shares": p.init_shares,
            "half_taken": p.half_done, "cost": round(cost),
            "realized": round(p.realized), "value": round(value),
            "pnl": round(value - cost),
            "pnl_pct": round((value / cost - 1) * 100, 2) if cost else 0.0})

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "open_positions": open_positions,
        "daily_eligible": daily_eligible,
        "skipped_no_slot": skipped_no_slot,
        "skipped_no_cash": skipped_no_cash,
        "params": {
            "start": days[0].strftime("%Y-%m-%d"), "end": days[-1].strftime("%Y-%m-%d"),
            "top_n": top_n, "fund_mode": fund_mode, "risk_pct": risk_pct,
            "max_positions": max_positions, "max_weight": max_weight,
            "fee_bp": fee_bp, "initial": initial, "min_turnover_eok": min_turnover,
            "require_c6": require_c6,
            "template_min": config.TEMPLATE_PASS_MIN,
            "sepa_threshold": config.SEPA_BUY_THRESHOLD,
            "momentum_weights": config.MOMENTUM_WEIGHTS,
        },
    }


def _mtm(p: Position, prices, idx_vals, today) -> float:
    return p.shares * _last_price(p, prices, idx_vals, today)


def _last_price(p: Position, prices, idx_vals, today) -> float:
    k = np.searchsorted(idx_vals[p.code], today.to_datetime64(), side="right")
    if k == 0:
        return p.entry
    return float(prices[p.code]["Close"].iloc[k - 1])


def _close_trade(p: Position, date, px, kind) -> dict:
    """p.realized 에는 절반 익절분과 이번 청산분이 모두 반영된 뒤 호출된다."""
    cost = p.init_shares * p.entry + p.fees        # 매수 수수료 포함 원가
    return {
        "code": p.code, "name": p.name, "category": p.category,
        "entry_date": p.entry_date.strftime("%Y-%m-%d"),
        "exit_date": date.strftime("%Y-%m-%d"),
        "days": (date - p.entry_date).days,
        "entry": round(p.entry), "exit": round(px),
        "stop": round(p.stop), "target": round(p.target),
        "shares": p.init_shares, "kind": kind,
        "half_taken": p.half_done,
        "cost": round(cost), "proceeds": round(p.realized),
        "pnl": round(p.realized - cost),
        "pnl_pct": round((p.realized / cost - 1) * 100, 2) if cost else 0.0,
        "sepa": p.sepa, "momentum": p.momentum,
    }


def main():
    ap = argparse.ArgumentParser(description="스크리너 규칙 백테스트")
    ap.add_argument("--cache", required=True, help="가격 캐시 pkl 경로")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--top", type=int, default=config.TOP_N)
    ap.add_argument("--fund-mode", default="neutral", choices=["neutral", "etf"])
    ap.add_argument("--risk", type=float, default=0.01, help="종목당 감수 비율")
    ap.add_argument("--max-positions", type=int, default=10)
    ap.add_argument("--max-weight", type=float, default=0.20, help="종목당 최대 비중")
    ap.add_argument("--fee-bp", type=float, default=5.0, help="편도 수수료+슬리피지 (bp)")
    ap.add_argument("--initial", type=float, default=10_000_000)
    ap.add_argument("--min-turnover", type=float, default=config.MIN_TURNOVER_EOK)
    ap.add_argument("--require-c6", action="store_true",
                    help="'52주 저가 대비 +30%%' 조건을 필수로 (저변동 상품 배제)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    data = load_cache(args.cache)
    res = run(data, args.start, args.end, args.top, args.fund_mode, args.risk,
              args.max_positions, args.max_weight, args.fee_bp, args.initial,
              args.min_turnover, args.require_c6)

    out = Path(args.out) if args.out else ROOT / "data" / f"backtest_{args.fund_mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    log.info("결과 저장: %s", out)

    eq = res["equity_curve"]
    log.info("최종 자산 %.0f원 (초기 %.0f) · 거래 %d건 · 미청산 %d",
             eq[-1]["equity"], args.initial, len(res["trades"]), len(res["open_positions"]))


if __name__ == "__main__":
    main()
