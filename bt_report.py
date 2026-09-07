"""백테스트 결과 분석 + HTML 리포트(docs/backtest.html) 생성

backtest.py가 만든 JSON을 읽어 성과 지표를 계산하고, 벤치마크(KODEX 200 ·
KOSPI) 매수후보유와 비교한다.

지표 정의
  CAGR      연평균 복리 수익률
  MDD       고점 대비 최대 낙폭
  Sharpe    (일간초과수익 평균 / 표준편차) × √252, 무위험수익률 0 가정
  Profit Factor  총이익 ÷ 총손실
  노출도    포지션을 하나라도 보유한 날의 비율
"""

import json
import math
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.report import _CSS, _esc


# ── 지표 ──────────────────────────────────────────────────────────────
def stats_from_curve(dates, values, initial) -> dict:
    s = pd.Series(values, index=pd.to_datetime(dates))
    ret = s.pct_change().dropna()
    years = (s.index[-1] - s.index[0]).days / 365.25
    total = s.iloc[-1] / initial - 1
    cagr = (s.iloc[-1] / initial) ** (1 / years) - 1 if years > 0 else 0.0
    dd = s / s.cummax() - 1
    vol = ret.std() * math.sqrt(252)
    sharpe = (ret.mean() / ret.std() * math.sqrt(252)) if ret.std() > 0 else 0.0
    downside = ret[ret < 0].std()
    sortino = (ret.mean() / downside * math.sqrt(252)) if downside and downside > 0 else 0.0
    return {
        "total_return": total * 100,
        "cagr": cagr * 100,
        "mdd": dd.min() * 100,
        "vol": vol * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "years": years,
        "final": float(s.iloc[-1]),
        "mdd_date": dd.idxmin().strftime("%Y-%m-%d"),
        "calmar": (cagr * 100) / abs(dd.min() * 100) if dd.min() < 0 else 0.0,
    }


def trade_stats(trades, open_positions) -> dict:
    if not trades:
        return {}
    pnl = [t["pnl"] for t in trades]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    kinds = {}
    for t in trades:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    holds = [t["days"] for t in trades]
    return {
        "n": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        "avg_win_pct": float(np.mean([t["pnl_pct"] for t in trades if t["pnl"] > 0])) if wins else 0.0,
        "avg_loss_pct": float(np.mean([t["pnl_pct"] for t in trades if t["pnl"] <= 0])) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy": sum(pnl) / len(trades),
        "best": max(pnl), "worst": min(pnl),
        "avg_hold": float(np.mean(holds)),
        "median_hold": float(np.median(holds)),
        "kinds": kinds,
        "open_n": len(open_positions),
    }


def yearly(dates, values) -> list:
    s = pd.Series(values, index=pd.to_datetime(dates))
    out = []
    for y, grp in s.groupby(s.index.year):
        prev = s[s.index < grp.index[0]]
        base = prev.iloc[-1] if len(prev) else grp.iloc[0]
        out.append({"year": int(y), "ret": (grp.iloc[-1] / base - 1) * 100,
                    "end": float(grp.iloc[-1])})
    return out


def benchmark_curve(px: pd.DataFrame, dates, initial, fee_bp=5.0) -> list:
    """매수후보유 자산곡선 — 첫날 시가 매수, 수수료 편도 1회."""
    idx = pd.to_datetime(dates)
    close = px["Close"]
    if close.index.tz is not None:
        close.index = close.index.tz_localize(None)
    aligned = close.reindex(idx, method="ffill").dropna()
    if aligned.empty:
        return []
    shares = (initial * (1 - fee_bp / 10000)) / aligned.iloc[0]
    return [float(v * shares) for v in aligned.reindex(idx, method="ffill").fillna(aligned.iloc[0])]


# ── 리포트 ────────────────────────────────────────────────────────────
_BT_CSS = """
.bt{max-width:1000px;margin:0 auto;padding:0 16px}
.bt h2{font-size:20px;font-weight:800;letter-spacing:-.02em;margin:38px 0 4px}
.bt h3{font-size:15px;font-weight:800;margin:22px 0 6px}
.bt p{margin:8px 0;color:var(--ink2);font-size:14px;line-height:1.7;word-break:keep-all}
.bt p b,.bt li b{color:var(--ink)}
.bt ul,.bt ol{margin:8px 0 8px 20px;color:var(--ink2);font-size:14px;line-height:1.7}
.bt li{margin:4px 0;word-break:keep-all}

.warnbox{
  margin:18px 0;padding:15px 17px;border-radius:11px;background:#2a1414;
  border:1px solid #5a1e1e;color:#fca5a5;font-size:13.5px;line-height:1.75;word-break:keep-all
}
.warnbox .ct{display:block;font-weight:800;color:#fecaca;margin-bottom:7px;font-size:14.5px}
.warnbox ol{margin:8px 0 0 18px;color:#f3b8b8}
.warnbox b{color:#fff1f1}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
.kpi .kl{font-size:10.5px;font-weight:700;letter-spacing:.08em;color:var(--ink3);text-transform:uppercase}
.kpi .kv{font-size:23px;font-weight:800;margin-top:3px;letter-spacing:-.02em}
.kpi .kn{font-size:11.5px;color:var(--ink2);margin-top:2px}
.pos{color:var(--good)} .neg{color:var(--bad)} .neu{color:var(--ink)}

table.bt-t{width:100%;border-collapse:collapse;font-size:13.5px;margin:12px 0}
table.bt-t th{
  text-align:right;padding:8px 10px;border-bottom:1px solid var(--line);
  font-size:10.5px;font-weight:700;letter-spacing:.07em;color:var(--ink3);text-transform:uppercase
}
table.bt-t th:first-child,table.bt-t td:first-child{text-align:left}
table.bt-t td{padding:8px 10px;border-bottom:1px solid #1b2436;text-align:right;
  font-variant-numeric:tabular-nums;color:var(--ink2)}
table.bt-t tbody tr:hover{background:var(--panel2)}
table.bt-t td.name{color:var(--ink);font-weight:600}
table.bt-t tr.hl td{background:#122b21}
table.bt-t tr.hl td.name{color:#6ee7b7}
table.bt-t tr.bench td{border-top:2px solid var(--line);color:var(--ink3)}
table.bt-t tr.bench td.name{color:var(--ink2)}
.twrap{overflow-x:auto}

.chart{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 12px 8px;margin:16px 0}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink2);
  padding:0 4px 10px}
.legend i{display:inline-block;width:11px;height:3px;border-radius:2px;margin-right:5px;
  vertical-align:middle}

.note{font-size:12.5px;color:var(--ink3);line-height:1.65;margin-top:6px;word-break:keep-all}
.backlink{display:inline-block;margin-top:10px;font-size:13px;color:var(--info);text-decoration:none}
.backlink:hover{text-decoration:underline}
@media (max-width:760px){
  .kpis{grid-template-columns:1fr 1fr}
  .bt h2{font-size:18px}
}
"""


def _svg_curve(series: dict, dates, height=280, width=940) -> str:
    """여러 자산곡선을 하나의 SVG 라인차트로. series = {label: (values, color)}"""
    pad_l, pad_r, pad_t, pad_b = 58, 12, 12, 26
    allv = [v for vals, _ in series.values() for v in vals if v is not None]
    if not allv:
        return ""
    lo, hi = min(allv), max(allv)
    span = (hi - lo) or 1
    lo -= span * 0.06
    hi += span * 0.06
    n = len(dates)

    def X(i): return pad_l + (width - pad_l - pad_r) * (i / max(1, n - 1))
    def Y(v): return pad_t + (height - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    # y 눈금
    grid = []
    for f in range(5):
        v = lo + (hi - lo) * f / 4
        y = Y(v)
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                    f'stroke="#26324a" stroke-width="1"/>')
        grid.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" text-anchor="end" '
                    f'font-size="10" fill="#64748b">{v/1e6:.0f}백만</text>')
    # x 눈금 (연 단위)
    years, seen = [], set()
    for i, d in enumerate(dates):
        y4 = d[:4]
        if y4 not in seen:
            seen.add(y4)
            years.append((i, y4))
    for i, y4 in years:
        years_x = X(i)
        grid.append(f'<text x="{years_x:.1f}" y="{height-8}" text-anchor="middle" '
                    f'font-size="10" fill="#64748b">{y4}</text>')

    paths = []
    for label, (vals, color) in series.items():
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals) if v is not None)
        paths.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                     f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')

    legend = "".join(
        f'<span><i style="background:{c}"></i>{_esc(l)}</span>'
        for l, (_, c) in series.items())

    return (f'<div class="chart"><div class="legend">{legend}</div>'
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'role="img" aria-label="자산곡선">{"".join(grid)}{"".join(paths)}</svg></div>')


def _svg_dd(dates, values, height=130, width=940) -> str:
    s = pd.Series(values)
    dd = (s / s.cummax() - 1) * 100
    pad_l, pad_r, pad_t, pad_b = 58, 12, 10, 22
    lo = float(dd.min()) * 1.08 or -1
    n = len(dates)
    def X(i): return pad_l + (width - pad_l - pad_r) * (i / max(1, n - 1))
    def Y(v): return pad_t + (height - pad_t - pad_b) * (v / lo)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(dd))
    area = f"{pad_l},{Y(0):.1f} " + pts + f" {X(n-1):.1f},{Y(0):.1f}"
    grid = []
    for f in range(3):
        v = lo * f / 2
        y = Y(v)
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#26324a"/>')
        grid.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" text-anchor="end" font-size="10" '
                    f'fill="#64748b">{v:.0f}%</text>')
    return (f'<div class="chart"><div class="legend"><span><i style="background:#f87171"></i>'
            f'고점 대비 낙폭</span></div>'
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">'
            f'{"".join(grid)}<polygon points="{area}" fill="#f8717133"/>'
            f'<polyline points="{pts}" fill="none" stroke="#f87171" stroke-width="1.6"/></svg></div>')


def _kpi(label, value, note, cls="neu") -> str:
    return (f'<div class="kpi"><div class="kl">{_esc(label)}</div>'
            f'<div class="kv {cls}">{value}</div><div class="kn">{_esc(note)}</div></div>')


def _sign(v: float) -> str:
    return "pos" if v > 0 else ("neg" if v < 0 else "neu")


def diagnose(res: dict, prices: dict, lookahead_days: int = 120) -> dict:
    """청산 규칙이 제대로 작동했는지 사후 검증한다.

    익절: 판 뒤에도 계속 올랐다면 고정 익절가가 승자를 자른 것이다.
    손절: 손절 뒤 매수가를 회복했다면 손절폭이 너무 좁았던 것이다.
    """
    up, back = [], []
    for t in res["trades"]:
        df = prices.get(t["code"])
        if df is None:
            continue
        after = df[df.index > t["exit_date"]].head(lookahead_days)
        if len(after) < 20:
            continue
        mx = float(after["High"].max())
        if t["kind"] == "익절":
            up.append((mx / t["exit"] - 1) * 100)
        elif t["kind"] == "손절":
            back.append((mx / t["entry"] - 1) * 100)
    out = {"n_win": len(up), "n_loss": len(back), "months": lookahead_days // 20}
    if up:
        arr = np.array(up)
        out.update(win_median=float(np.median(arr)),
                   win_over10=float((arr >= 10).mean() * 100),
                   win_over30=float((arr >= 30).mean() * 100))
    if back:
        arr = np.array(back)
        out.update(loss_median=float(np.median(arr)),
                   loss_recovered=float((arr > 0).mean() * 100))

    # 슬롯을 장기 점유한 미청산 포지션
    stuck = sorted(res["open_positions"],
                   key=lambda o: o["entry_date"])[:5]
    out["stuck"] = [{"name": o["name"], "entry_date": o["entry_date"],
                     "pnl_pct": o["pnl_pct"]} for o in stuck
                    if o["entry_date"] < res["params"]["start"][:4] + "-12-31"]
    out["skipped_no_slot"] = res.get("skipped_no_slot", 0)
    return out



_VERDICT = """
  <h3>① 추적 손절 — <span style="color:var(--bad)">효과 없음. 오히려 나빠졌다</span></h3>
  <p>가장 기대했던 처방인데 <b>틀렸습니다.</b> 고정 익절가를 없애고 최고가에서
    일정 % 아래로 손절가를 따라 올리게 했더니, 총수익이 기준 +12.9%에서
    <b>추적 15% 기준 +5.9%로 떨어졌습니다.</b> 폭을 넓힐수록(10% → 15% → 20%) 더 나빠졌습니다.</p>
  <p>진단 자체는 맞았습니다. 승자는 실제로 풀려서, 최대 이익 거래가 +29.9%(고정 익절 상한)에서
    <b>+120%</b>까지 늘었습니다. 문제는 그 대가입니다. 추적 손절은 <b>고점에서 항상 그 폭만큼
    되돌려주고 나옵니다.</b> +20% 갔다가 15% 되돌리면 +2%에 청산됩니다.</p>
  <p>그 결과 <b>거래의 39%가 −5%~+5% 사이 무승부로 끝났습니다</b>(기준 24%).
    +5%를 넘긴 거래는 63건에서 28건으로 줄었습니다. 소수의 큰 승자가 늘어난 것보다,
    <b>중간 크기 승자가 무승부로 바뀐 손실이 더 컸습니다.</b></p>

  <h3>② ATR 손절 — <span style="color:var(--good)">효과 있음</span></h3>
  <p>손절폭을 3~10% 고정에서 <b>그 종목이 실제로 움직이는 폭(ATR 14일 × 3배)</b>에
    맞췄습니다. 총수익 +16.8%로 소폭 개선이지만, <b>최대 낙폭이 −24.6%에서 −11.9%로 절반</b>이 됐고
    승률 31%→38%, PF 0.99→1.08로 모두 좋아졌습니다.</p>
  <p>변동성이 큰 상품은 넓게, 작은 상품은 좁게 잡히니 <b>되돌림에 털리는 일이 줄었습니다.</b>
    ±5% 무승부 거래가 24%에서 8%로 떨어진 것이 그 증거입니다.</p>

  <h3>③ ‘52주 저가 +30%’ 필수 — <span style="color:var(--good)">효과 있음 (단, 낙폭 악화)</span></h3>
  <p>채권·단기금리 ETF가 슬롯을 영구 점유하던 문제가 사라졌습니다. 거래가 211건에서
    <b>464건</b>으로 늘고 총수익도 +39.4%로 세 배가 됐습니다. 다만 자금이 계속 회전하면서
    <b>최대 낙폭이 −45.6%로 크게 나빠졌습니다.</b> 이건 단독으로 쓰기 어렵습니다.</p>

  <h3>★ ②+③ 조합이 가장 좋았다 — 지금 사이트에 적용된 설정</h3>
  <p><b>ATR 손절 + ‘52주 저가 +30%’ 필수</b>를 함께 적용하면 총수익 <b>+76.3%</b>
    (CAGR +7.7%), 최대 낙폭 −28.1%, 승률 <b>45%</b>, PF <b>1.31</b>로
    모든 지표가 기준보다 낫습니다. ③이 슬롯을 풀어 기회를 늘리고, ②가 그 기회를
    되돌림에서 지켜 주는 조합입니다.</p>
  <p>여기에 ①(추적 손절)을 더하면 오히려 +25.6%로 다시 떨어집니다. 세 개를 다 넣는 게
    답이 아니었습니다.</p>
  <p class="note">표의 ‘②+③ 손절만 교체’(+79.0%)는 손절가를 포지션 관리에만 쓰고 SEPA
    손익비 점수에는 반영하지 않은 초기 실험입니다. 실제 사이트는 손절가가 화면에 표시되고
    점수에도 들어가야 하므로 <code>calculate_stop_loss()</code> 안에 넣었고, 그 경로로 다시
    돌린 값이 위의 +76.3%입니다. 둘의 차이는 통과 종목이 미세하게 달라진 데서 옵니다.</p>
  <p><b>이 설정이 현재 스크리너의 기본값입니다.</b>
    <code>config.py</code>의 <code>STOP_MODE = "swing"</code>,
    <code>REQUIRE_52W_LOW_CRITERION = False</code>로 되돌리면 원본 규칙으로 돌아갑니다.</p>

  <div class="warnbox" style="margin-top:22px">
    <span class="ct">그래도 매수후보유를 이기지 못한다</span>
    가장 좋은 조합(②+③)도 <b>+79.0% / CAGR +7.9%</b>입니다. 같은 기간 KODEX 200을
    그냥 사서 들고 있으면 <b>+370.4% / CAGR +22.4%</b>였습니다. 위험 대비로 봐도
    Sharpe 0.54 대 0.87로 밀립니다.<br><br>
    이 기간이 KOSPI가 세 배 넘게 오른 <b>이례적 강세장</b>이었다는 점은 감안해야 합니다.
    추세를 따라 들어갔다 나왔다 하는 전략은 이런 국면에서 구조적으로 뒤집니다.
    하지만 <b>이 백테스트가 보여주는 것은 그것뿐</b>이고, 다른 국면에서 낫다는 증거는
    여기에 없습니다. 게다가 생존편향 때문에 위 숫자들은 실제보다 좋게 나온 값입니다.
  </div>
"""

def _diagnosis(d: dict) -> str:
    if not d or not d.get("n_win"):
        return ""
    stuck_html = ""
    if d.get("stuck"):
        items = "".join(
            f"<li><b>{_esc(x['name'])}</b> — {_esc(x['entry_date'])} 진입, "
            f"백테스트 끝까지 미청산 ({x['pnl_pct']:+.1f}%)</li>" for x in d["stuck"])
        stuck_html = f"""
  <h3>③ 저변동 상품이 슬롯을 영구 점유한다</h3>
  <p>채권·단기금리 ETF는 <b>천천히, 거의 일직선으로</b> 오릅니다. 그래서
    Phase 2로 분류되고 트렌드 템플릿도 <b>정확히 7/8</b>을 받습니다. 8개 중 유일하게
    실패하는 것이 ‘52주 저가 대비 +30% 이상’인데, 통과 기준이 7개라 그것만 빠져도
    관문을 넘습니다.</p>
  <p>문제는 그다음입니다. 손절가(−3~10%)에도 익절가(+30%)에도 <b>몇 년째 닿지 않아</b>
    포지션이 끝나지 않습니다. 아래 종목들은 2019년 초에 사서 백테스트가 끝날 때까지
    자리를 차지했습니다.</p>
  <ul>{items}</ul>
  <p>그 결과 슬롯 부족으로 넘긴 신호가 <b>{d['skipped_no_slot']:,}회</b>였습니다.
    ‘+30% 조건 필수’ 변형은 이것 하나만 바꾼 것이고, 거래 수가 배 이상 늘었습니다.</p>"""

    return f"""
  <h2>왜 졌나 — 세 가지 진단</h2>

  <h3>① 고정 익절가가 승자를 자른다</h3>
  <p>익절로 청산한 거래를 <b>판 뒤 약 {d['months']}개월</b> 더 따라가 봤습니다.
    청산가 대비 최고가가 <b>중앙값 {d['win_median']:+.1f}%</b> 더 올랐습니다.
    {d['win_over10']:.0f}%는 10% 이상, <b>{d['win_over30']:.0f}%는 30% 이상</b> 더 갔습니다.</p>
  <p>이 규칙의 최종 익절은 <b>매수가 +30% 고정</b>입니다. 추세추종에서 수익은 소수의
    큰 승자에서 나오는데, 고정 익절가는 바로 그 승자를 중간에 끊습니다. 미너비니의
    원래 방식은 고정 목표가가 아니라 <b>추적 손절(trailing stop)</b>로 끝까지 따라갑니다.</p>

  <h3>② 손절폭이 ETF에는 너무 좁다</h3>
  <p>손절로 청산한 거래 중 <b>{d['loss_recovered']:.0f}%가 약 {d['months']}개월 안에
    원래 매수가를 회복</b>했습니다(중앙값 {d['loss_median']:+.1f}%).
    손절이 위험을 막은 게 아니라, 되돌림에 흔들려 나온 경우가 많았다는 뜻입니다.</p>
  <p>손절폭은 3~10%로 강제되는데, 이는 개별 성장주 기준입니다. ETF는 수십 종목을
    담은 바구니라 개별주보다 덜 움직이지만 <b>되돌림은 더 자주</b> 옵니다.</p>
  {stuck_html}"""




def build_report(res: dict, bench: dict, variants: dict = None, diag: dict = None) -> str:
    p = res["params"]
    eq = res["equity_curve"]
    dates = [e["date"] for e in eq]
    vals = [e["equity"] for e in eq]
    initial = p["initial"]

    st = stats_from_curve(dates, vals, initial)
    ts = trade_stats(res["trades"], res["open_positions"])
    yr = yearly(dates, vals)

    series = {"전략": (vals, "#34d399")}
    bstats = {}
    for label, (curve, color) in bench.items():
        if curve:
            series[label] = (curve, color)
            bstats[label] = stats_from_curve(dates, curve, initial)

    ycols = "".join(f"<th>{y['year']}</th>" for y in yr)
    yrow = "".join(f'<td class="{_sign(y["ret"])}">{y["ret"]:+.1f}%</td>' for y in yr)
    ybench = ""
    for label in bench:
        if label in bstats:
            by = yearly(dates, bench[label][0])
            ybench += (f'<tr><td class="name">{_esc(label)}</td>' +
                       "".join(f'<td class="{_sign(v["ret"])}">{v["ret"]:+.1f}%</td>' for v in by) +
                       f'<td class="{_sign(bstats[label]["total_return"])}">'
                       f'{bstats[label]["total_return"]:+.1f}%</td></tr>')

    kinds = ts.get("kinds", {})
    kind_rows = "".join(
        f'<tr><td class="name">{_esc(k)}</td><td>{v}</td>'
        f'<td>{v / ts["n"] * 100:.1f}%</td></tr>'
        for k, v in sorted(kinds.items(), key=lambda x: -x[1]))

    tr_sorted = sorted(res["trades"], key=lambda t: t["pnl"], reverse=True)

    def trow(t):
        return (f'<tr><td class="name">{_esc(t["name"][:24])}</td>'
                f'<td>{_esc(t["entry_date"])}</td><td>{t["days"]}일</td>'
                f'<td>{t["entry"]:,}</td><td>{t["exit"]:,}</td>'
                f'<td class="{_sign(t["pnl"])}">{t["pnl"]:+,}</td>'
                f'<td class="{_sign(t["pnl_pct"])}">{t["pnl_pct"]:+.1f}%</td>'
                f'<td>{_esc(t["kind"])}</td></tr>')

    best5 = "".join(trow(t) for t in tr_sorted[:5])
    worst5 = "".join(trow(t) for t in tr_sorted[-5:])

    cat = {}
    for t in res["trades"]:
        c = cat.setdefault(t["category"], {"n": 0, "pnl": 0, "win": 0})
        c["n"] += 1
        c["pnl"] += t["pnl"]
        c["win"] += 1 if t["pnl"] > 0 else 0
    cat_rows = "".join(
        f'<tr><td class="name">{_esc(k)}</td><td>{v["n"]}</td>'
        f'<td>{v["win"] / v["n"] * 100:.0f}%</td>'
        f'<td class="{_sign(v["pnl"])}">{v["pnl"]:+,}</td></tr>'
        for k, v in sorted(cat.items(), key=lambda x: -x[1]["pnl"]))

    elig = res["daily_eligible"]
    zero_days = sum(1 for x in elig if x == 0)
    exposure = sum(1 for e in eq if e["positions"] > 0) / len(eq) * 100
    avg_pos = float(np.mean([e["positions"] for e in eq]))

    alt_html = ""
    if variants:
        rows = [("규칙 그대로 (기준)", st, ts)]
        for label, v in variants.items():
            vs = stats_from_curve([e["date"] for e in v["equity_curve"]],
                                  [e["equity"] for e in v["equity_curve"]],
                                  v["params"]["initial"])
            vt = trade_stats(v["trades"], v["open_positions"])
            rows.append((label, vs, vt))
        body = "".join(
            f'<tr{" class=\"hl\"" if lab.startswith("★") else ""}>'
            f'<td class="name">{_esc(lab)}</td>'
            f'<td class="{_sign(v["total_return"])}">{v["total_return"]:+.1f}%</td>'
            f'<td class="{_sign(v["cagr"])}">{v["cagr"]:+.1f}%</td>'
            f'<td class="neg">{v["mdd"]:.1f}%</td>'
            f'<td>{v["sharpe"]:.2f}</td><td>{t["n"]:,}</td>'
            f'<td>{t["win_rate"]:.0f}%</td>'
            f'<td class="{_sign(t["profit_factor"] - 1)}">{t["profit_factor"]:.2f}</td></tr>'
            for lab, v, t in rows)
        bbody = "".join(
            f'<tr class="bench"><td class="name">{_esc(label)} 매수후보유</td>'
            f'<td class="{_sign(bstats[label]["total_return"])}">{bstats[label]["total_return"]:+.1f}%</td>'
            f'<td class="{_sign(bstats[label]["cagr"])}">{bstats[label]["cagr"]:+.1f}%</td>'
            f'<td class="neg">{bstats[label]["mdd"]:.1f}%</td>'
            f'<td>{bstats[label]["sharpe"]:.2f}</td><td>—</td><td>—</td><td>—</td></tr>'
            for label in bench if label in bstats)
        alt_html = f"""
  <h2>세 가지 처방을 검증했다</h2>
  <p>앞의 진단에서 나온 세 가지 문제에 각각 대응하는 수정안을 만들어,
     같은 기간·같은 조건으로 다시 돌렸습니다. 조합도 함께 시험했습니다.</p>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>구분</th><th>총수익</th><th>CAGR</th><th>MDD</th>
    <th>Sharpe</th><th>거래</th><th>승률</th><th>PF</th></tr></thead>
    <tbody>{body}{bbody}</tbody></table></div>
  <p class="note">PF(손익비) = 총이익 ÷ 총손실. 1을 넘어야 이익이 납니다.
    ‘펀드 품질 채점’은 과거 순자산·NAV가 없어 <b>오늘 값</b>을 넣은 것이라 미래 정보가 섞여 있습니다.</p>"""

    bench_kpis = ""
    for label in bench:
        if label in bstats:
            b = bstats[label]
            bench_kpis += _kpi(f"{label} 매수후보유", f"{b['total_return']:+.0f}%",
                               f"CAGR {b['cagr']:+.1f}% · MDD {b['mdd']:.0f}%",
                               _sign(b["total_return"]))

    diag_html = _diagnosis(diag) if diag else ""
    verdict_html = _VERDICT if variants else ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    wr = ts["win_rate"]
    pf = ts["profit_factor"]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>백테스트 | 국내 ETF 모멘텀 × SEPA 스크리너</title>
<meta name="description" content="스크리너 규칙을 과거 데이터에 그대로 적용한 백테스트 결과와 그 한계">
<style>{_CSS}{_BT_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">백테스트</div>
    <h1>이 규칙을 과거에 적용했다면</h1>
    <p class="sub">{_esc(p['start'])} ~ {_esc(p['end'])} · {st['years']:.1f}년 ·
      초기자본 {initial / 1e4:,.0f}만원</p>
    <a class="backlink" href="./index.html">← 스크리너</a>
    &nbsp;&nbsp;<a class="backlink" href="./guide.html">사용법 →</a>
  </div>
</header>

<div class="bt">

  <div class="warnbox">
    <span class="ct">결과를 믿기 전에 반드시 읽어야 할 네 가지</span>
    <ol>
      <li><b>생존편향.</b> 유니버스가 '오늘 상장되어 있는' ETF 목록입니다. 그사이
        상장폐지된 ETF는 처음부터 목록에 없습니다. <b>망한 상품이 통째로 빠진
        경기입니다.</b> 이 편향은 제거할 방법이 없고, 결과를 실제보다 좋게 만듭니다.</li>
      <li><b>과거일수록 유니버스가 얇습니다.</b> 국내 ETF는 최근 몇 년 사이 폭증했습니다.
        2019년 시점에 200거래일 이상 쌓인 종목은 200여 개뿐이었고, 지금은 875개입니다.</li>
      <li><b>펀드 품질 40점은 과거 재구성이 불가능합니다.</b> 과거 시점의 순자산·NAV
        기록이 없어, 기본 결과는 이 항목을 <b>전 종목 20점 고정</b>으로 두고 계산했습니다.
        실제 사이트가 매기는 점수와는 다릅니다.</li>
      <li><b>체결을 이상적으로 가정했습니다.</b> 신호 다음날 시가, 그리고 손절·익절가에
        정확히 체결된다고 봤습니다. 실제로는 호가 스프레드와 미체결이 있습니다.
        수수료·슬리피지는 편도 {p['fee_bp']:.0f}bp만 반영했습니다.</li>
    </ol>
  </div>

  <h2>성과 요약</h2>
  <div class="kpis">
    {_kpi("총수익률", f"{st['total_return']:+.0f}%", f"{initial / 1e4:,.0f}만 → {st['final'] / 1e4:,.0f}만원", _sign(st['total_return']))}
    {_kpi("연평균 (CAGR)", f"{st['cagr']:+.1f}%", f"{st['years']:.1f}년 복리", _sign(st['cagr']))}
    {_kpi("최대 낙폭 (MDD)", f"{st['mdd']:.1f}%", f"저점 {st['mdd_date']}", "neg")}
    {_kpi("Sharpe", f"{st['sharpe']:.2f}", f"변동성 {st['vol']:.1f}% · Calmar {st['calmar']:.2f}", "neu")}
    {bench_kpis}
  </div>

  {_svg_curve(series, dates)}
  {_svg_dd(dates, vals)}

  <h2>연도별 수익률</h2>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>구분</th>{ycols}<th>전체</th></tr></thead>
  <tbody>
    <tr><td class="name">전략</td>{yrow}
      <td class="{_sign(st['total_return'])}">{st['total_return']:+.1f}%</td></tr>
    {ybench}
  </tbody></table>
  </div>
  <p class="note">{yr[0]['year']}년과 {yr[-1]['year']}년은 부분 기간입니다.</p>

  <h2>거래 통계</h2>
  <div class="kpis">
    {_kpi("총 거래", f"{ts['n']}건", f"연 {ts['n'] / st['years']:.0f}건 · 미청산 {ts['open_n']}건", "neu")}
    {_kpi("승률", f"{wr:.0f}%", f"평균이익 {ts['avg_win_pct']:+.1f}% / 평균손실 {ts['avg_loss_pct']:+.1f}%", _sign(wr - 50))}
    {_kpi("손익비 (PF)", f"{pf:.2f}", "총이익 ÷ 총손실", _sign(pf - 1))}
    {_kpi("건당 기대값", f"{ts['expectancy']:+,.0f}원", f"평균 보유 {ts['avg_hold']:.0f}일", _sign(ts['expectancy']))}
  </div>

  <h3>청산 유형</h3>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>유형</th><th>건수</th><th>비중</th></tr></thead>
  <tbody>{kind_rows}</tbody></table>
  </div>
  <p class="note">‘부분익절+본전청산’은 1차 익절에서 절반을 판 뒤 손절가를 매수가로 올렸고,
    이후 그 가격에 걸려 나머지를 정리한 경우입니다. 절반의 이익이 남아 대체로 소폭 플러스입니다.</p>

  <h3>분류별</h3>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>분류</th><th>거래</th><th>승률</th><th>누적손익</th></tr></thead>
  <tbody>{cat_rows}</tbody></table>
  </div>

  <h3>가장 크게 번 거래 5건</h3>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>ETF</th><th>진입일</th><th>보유</th><th>진입</th><th>청산</th>
    <th>손익</th><th>%</th><th>유형</th></tr></thead><tbody>{best5}</tbody></table>
  </div>

  <h3>가장 크게 잃은 거래 5건</h3>
  <div class="twrap">
  <table class="bt-t"><thead><tr><th>ETF</th><th>진입일</th><th>보유</th><th>진입</th><th>청산</th>
    <th>손익</th><th>%</th><th>유형</th></tr></thead><tbody>{worst5}</tbody></table>
  </div>

  <h2>얼마나 자주 신호가 났나</h2>
  <p>전체 {len(elig):,}거래일 중 <b>매수 적격이 하나도 없던 날이 {zero_days:,}일
    ({zero_days / len(elig) * 100:.0f}%)</b>입니다. 하루 평균 적격 종목은
    {np.mean(elig):.1f}개였습니다.</p>
  <p>포지션을 하나라도 들고 있던 날은 <b>{exposure:.0f}%</b>, 평균 보유 종목 수는
    <b>{avg_pos:.1f}개</b>였습니다(최대 {p['max_positions']}개). 나머지는 현금입니다.
    이 전략이 시장에 늘 들어가 있지 않다는 뜻이고, 벤치마크와 단순 비교하기 어려운 이유이기도 합니다.</p>

  {diag_html}

  {alt_html}

  {verdict_html}

  <h2>실행 규칙</h2>
  <ul>
    <li><b>진입</b> — 신호일 종가 기준 3관문(Phase 2 · 템플릿 {p['template_min']}/8 ·
      SEPA {p['sepa_threshold']}점) 통과 → <b>다음 거래일 시가</b> 매수.</li>
    <li><b>수량</b> — 자본의 {p['risk_pct'] * 100:.0f}%를 잃는 지점이 손절가가 되도록 역산.
      종목당 최대 비중 {p['max_weight'] * 100:.0f}%, 동시 보유 최대 {p['max_positions']}종목.</li>
    <li><b>청산</b> — 손절가 도달 시 전량 / 1차 익절 도달 시 절반 + 손절가를 매수가로 /
      최종 익절 도달 시 나머지. 가격은 진입 시점 값으로 고정.</li>
    <li><b>유니버스</b> — 레버리지·인버스 제외, 20일 평균 거래대금
      {p['min_turnover_eok']:.0f}억원 이상, 200거래일 이상 상장.
      순자산 하한은 과거 값이 없어 적용하지 않았습니다.</li>
    <li><b>비용</b> — 매수·매도 각각 {p['fee_bp']:.0f}bp(왕복 {p['fee_bp'] * 2:.0f}bp).</li>
  </ul>

  <p style="margin-top:26px"><a class="backlink" href="./index.html">← 스크리너로 돌아가기</a></p>
</div>

<footer>
  <div class="wrap">
    <p><b>재현</b> — <code>python backtest.py --cache &lt;가격캐시&gt; --start {p['start']}</code>
       후 <code>python bt_report.py</code>. 규칙 코드는 실시간 스캔과 동일한
       <code>src/momentum.py</code> · <code>src/phase_indicators.py</code> · <code>src/sepa.py</code>를 씁니다.</p>
    <p>생성 {now} · 가격 데이터 yfinance</p>
    <p style="color:#4a5568">과거 성과는 미래 수익을 보장하지 않습니다. 백테스트는 실제 매매가
       아니며, 위에 적은 편향과 가정이 결과를 실제보다 좋게 만듭니다.
       본 페이지는 정보 제공 목적이며 투자 자문이 아닙니다.</p>
  </div>
</footer>

</body>
</html>"""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--alt", action="append", default=None,
                    help="비교 변형: '라벨=경로.json' 형식, 여러 번 지정 가능")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", default="docs/backtest.html")
    a = ap.parse_args()

    res = json.loads(Path(a.result).read_text(encoding="utf-8"))
    data = pickle.load(open(a.cache, "rb"))

    dates = [e["date"] for e in res["equity_curve"]]
    initial = res["params"]["initial"]
    bench = {}
    if "069500" in data["prices"]:
        bench["KODEX 200"] = (benchmark_curve(data["prices"]["069500"], dates, initial), "#60a5fa")
    bench["KOSPI"] = (benchmark_curve(data["bm"], dates, initial), "#94a3b8")

    variants = {}
    if a.alt:
        for spec in a.alt:
            label, path = spec.split("=", 1)
            variants[label] = json.loads(Path(path).read_text(encoding="utf-8"))

    diag = diagnose(res, data["prices"])
    html = build_report(res, bench, variants or None, diag)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"리포트 저장: {out}")

    st = stats_from_curve(dates, [e["equity"] for e in res["equity_curve"]], initial)
    ts = trade_stats(res["trades"], res["open_positions"])
    print(f"  총수익 {st['total_return']:+.1f}% · CAGR {st['cagr']:+.1f}% · "
          f"MDD {st['mdd']:.1f}% · Sharpe {st['sharpe']:.2f}")
    print(f"  거래 {ts['n']}건 · 승률 {ts['win_rate']:.0f}% · PF {ts['profit_factor']:.2f} · "
          f"기대값 {ts['expectancy']:+,.0f}원")
    for k, (c, _) in bench.items():
        if c:
            b = stats_from_curve(dates, c, initial)
            print(f"  [{k}] 총수익 {b['total_return']:+.1f}% · CAGR {b['cagr']:+.1f}% · MDD {b['mdd']:.1f}%")


if __name__ == "__main__":
    main()
