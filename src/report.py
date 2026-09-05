"""GitHub Pages용 HTML 리포트 생성 — 국내 ETF판

원본(snp_sepa_mmt)의 정보 설계를 그대로 따른다.
  - 요약을 먼저, 상세는 접어서 (시장 국면 → 랭킹 → 종목별 내역)
  - 8개 Trend Template 조건을 점 8개로 인코딩 → 20종목을 한눈에 비교
  - SEPA 점수 막대에 매수 임계선(60점)을 표시해 합격/불합격이 형태로 보이게

원본과 다른 표시:
  - 티커가 아니라 ETF 이름이 식별자다. 이름을 크게, 6자리 코드를 작게 둔다.
  - 통화가 원화라 소수점을 쓰지 않는다.
  - 펀더멘털 자리에 펀드 품질(순자산·거래대금·괴리율)이 들어간다.
"""

import html
from datetime import datetime
from typing import Dict, List

from .sepa import CRITERIA_LABELS, COMPONENT_MAX, COMPONENT_LABELS

PHASE_META = {
    1: ("베이스", "p1"),
    2: ("상승추세", "p2"),
    3: ("분산·과열", "p3"),
    4: ("하락추세", "p4"),
}

_CSS = """
:root{
  --bg:#0b1220; --panel:#131c2e; --panel2:#1a2438; --line:#26324a;
  --ink:#e6ecf7; --ink2:#94a3b8; --ink3:#64748b;
  --accent:#f5a524;           /* 모멘텀 = 열기 */
  --good:#34d399; --warn:#fbbf24; --bad:#f87171; --info:#60a5fa;
}
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',
    'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.55;
  -webkit-font-smoothing:antialiased; font-size:15px;
}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
.num{font-variant-numeric:tabular-nums}

/* ── 헤더 ───────────────────────────────────────────── */
header{
  background:linear-gradient(160deg,#16203a 0%,#0e1728 100%);
  border-bottom:1px solid var(--line); padding:30px 16px 26px;
}
.eyebrow{
  font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px
}
h1{font-size:clamp(21px,4.4vw,29px);font-weight:800;letter-spacing:-.02em;text-wrap:balance}
.sub{margin-top:7px;font-size:13px;color:var(--ink2)}
.sub b{color:var(--ink);font-weight:600}
.exclu{
  display:inline-block;margin-top:9px;padding:3px 9px;border-radius:6px;
  background:#2a1c14;border:1px solid #5a3a1e;color:#fcd34d;font-size:11.5px;font-weight:600
}

/* ── 시장 요약 ──────────────────────────────────────── */
.market{
  display:grid;grid-template-columns:minmax(190px,1.25fr) repeat(4,1fr);
  gap:10px;margin:22px 0 26px
}
.mcard{
  background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px
}
.mcard.bm{border-color:#3b5680;background:linear-gradient(150deg,#17253d,#131c2e)}
.mlabel{font-size:10.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.mval{font-size:23px;font-weight:800;letter-spacing:-.02em;margin-top:3px}
.mnote{font-size:11.5px;color:var(--ink2);margin-top:3px}
.mcard.bm .mnote{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}

/* ── 섹션 ───────────────────────────────────────────── */
.sec{margin:30px 0}
.sec-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.sec h2{font-size:17px;font-weight:800;letter-spacing:-.01em}
.sec-note{font-size:12.5px;color:var(--ink2)}

/* ── 랭킹 행 ────────────────────────────────────────── */
.cols{
  display:grid;
  grid-template-columns:34px minmax(0,1fr) 74px 62px 84px 96px 148px 106px;
  gap:10px;align-items:center
}
.colhead{
  padding:0 14px 7px;font-size:10.5px;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ink3);border-bottom:1px solid var(--line)
}
.row{
  background:var(--panel);border:1px solid var(--line);border-radius:11px;
  margin-top:7px;overflow:hidden
}
.row.buy{border-color:#2f6b52;background:linear-gradient(100deg,#13251d 0%,var(--panel) 42%)}
.row>summary{padding:12px 14px;cursor:pointer;list-style:none}
.row>summary::-webkit-details-marker{display:none}
.row>summary:hover{background:var(--panel2)}
.row[open]>summary{background:var(--panel2);border-bottom:1px solid var(--line)}

.rank{font-size:17px;font-weight:800;color:var(--accent);text-align:center}
.tk{font-size:14.5px;font-weight:700;letter-spacing:-.01em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tk .nm{display:block;font-size:11px;font-weight:400;color:var(--ink3);letter-spacing:.04em}
.sect{
  display:inline-block;font-size:11px;font-weight:700;padding:2.5px 7px;
  border-radius:5px;background:#22304a;color:#a9bdd9;white-space:nowrap
}
.mom{font-size:15px;font-weight:700;color:var(--accent)}
.mom small{display:block;font-size:10px;font-weight:400;color:var(--ink3);letter-spacing:.04em}

.phase{
  display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;
  white-space:nowrap
}
.p1{background:#1e3a5f;color:#7dd3fc}
.p2{background:#14432f;color:#6ee7b7}
.p3{background:#42320c;color:#fcd34d}
.p4{background:#451a1a;color:#fca5a5}

/* 8개 조건 점 */
.dots{display:flex;gap:3px;align-items:center}
.dot{width:9px;height:9px;border-radius:2px;background:#31405c}
.dot.on{background:var(--good)}
.dots .cnt{margin-left:5px;font-size:11.5px;font-weight:700;color:var(--ink2)}

/* SEPA 점수 막대 */
.bar{position:relative;height:19px;background:#1d2941;border-radius:4px;overflow:hidden}
.bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;display:block}
.bar .mark{position:absolute;top:0;bottom:0;width:2px;background:#6b7ea0;opacity:.85}
.bar .txt{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:flex-end;
  padding-right:7px;font-size:11.5px;font-weight:800;color:#fff;
  text-shadow:0 1px 2px rgba(0,0,0,.6)
}
.barnote{font-size:10px;color:var(--ink3);margin-top:2px;letter-spacing:.03em}

.px{text-align:right;font-size:14px;font-weight:700}
.px small{display:block;font-size:10.5px;font-weight:400;color:var(--ink3);margin-top:1px}

/* ── 상세 ───────────────────────────────────────────── */
.detail{padding:15px 15px 17px;background:#101828}
.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.dtitle{
  font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);margin-bottom:9px
}
.comp{display:flex;align-items:center;gap:9px;margin-bottom:6px;font-size:12.5px}
.comp .cn{width:66px;flex-shrink:0;color:var(--ink2)}
.comp .cb{flex:1;height:7px;background:#1d2941;border-radius:3px;overflow:hidden}
.comp .cb>i{display:block;height:100%;background:var(--info);border-radius:3px}
.comp .cv{width:56px;flex-shrink:0;text-align:right;font-weight:700}

.crit{display:flex;align-items:center;gap:7px;margin-bottom:4px;font-size:12.5px}
.crit .ck{width:14px;flex-shrink:0;font-weight:800;text-align:center}
.crit.ok .ck{color:var(--good)}
.crit.no .ck{color:var(--bad)}
.crit.no span{color:var(--ink3)}

.plan{
  display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0 12px;
  padding:11px;background:var(--panel);border:1px solid var(--line);border-radius:9px
}
.plan div{text-align:center}
.plan .pl{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}
.plan .pv{font-size:15px;font-weight:800;margin-top:2px}
.pv.stop{color:var(--bad)} .pv.mid{color:var(--warn)} .pv.tgt{color:var(--good)}

.fund{
  display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 12px;
  padding:10px 11px;background:var(--panel);border:1px solid var(--line);border-radius:9px
}
.fund div{text-align:center}
.fund .fl{font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--ink3);
  word-break:keep-all;line-height:1.35}
.fund .fv{font-size:14px;font-weight:700;margin-top:2px}

.why{list-style:none;font-size:12.5px;color:var(--ink2)}
.why li{padding:2.5px 0 2.5px 13px;position:relative}
.why li:before{content:'';position:absolute;left:2px;top:11px;width:4px;height:4px;
  border-radius:50%;background:var(--ink3)}
.block{
  margin-top:11px;padding:8px 11px;border-radius:7px;font-size:12.5px;
  background:#2a1c14;border:1px solid #5a3a1e;color:#fcd34d
}
.block.pass{background:#122b21;border-color:#2f6b52;color:#6ee7b7}

/* ── 푸터 ───────────────────────────────────────────── */
footer{
  margin-top:44px;padding:24px 16px 32px;border-top:1px solid var(--line);
  background:#0a101c;font-size:12px;color:var(--ink3)
}
footer p{margin-bottom:5px}
footer b{color:var(--ink2)}

/* ── 모바일 ─────────────────────────────────────────── */
@media (max-width:880px){
  .market{grid-template-columns:1fr 1fr}
  .mcard.bm{grid-column:1/-1}
  .mcard.bm .mnote{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
  .colhead{display:none}
  .cols{grid-template-columns:30px 1fr auto;grid-template-areas:
    "rank tk   phase"
    "rank sect mom"
    "dots dots dots"
    "bar  bar  bar"
    "px   px   px";
    gap:5px 9px}
  .cols>.rank{grid-area:rank;align-self:start;padding-top:2px}
  .cols>.tk{grid-area:tk;white-space:normal}
  .cols>.sectwrap{grid-area:sect}
  .cols>.momwrap{grid-area:mom;text-align:right}
  .cols>.phasewrap{grid-area:phase;text-align:right}
  .cols>.dotswrap{grid-area:dots;margin-top:5px}
  .dotswrap:before{
    content:'트렌드 템플릿';font-size:10px;font-weight:700;letter-spacing:.06em;
    color:var(--ink3);margin-right:7px
  }
  .dots{display:inline-flex;vertical-align:middle}
  .cols>.barwrap{grid-area:bar;margin-top:3px}
  .cols>.pxwrap{grid-area:px;display:flex;gap:14px;align-items:baseline;
    justify-content:flex-start;margin-top:6px;text-align:left}
  .px small{display:inline;margin:0}
  .px{text-align:left}
  .dgrid{grid-template-columns:1fr;gap:16px}
  .plan{grid-template-columns:repeat(2,1fr)}
  .fund{gap:6px;padding:9px 8px}
  .fund .fl{font-size:9.5px;letter-spacing:0}
  .fund .fv{font-size:12.5px}
}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _won(v, dash="—") -> str:
    """원화 표기 — 소수점 없이."""
    if v is None:
        return dash
    return f"{v:,.0f}원"


def _fmt(v, digits=2, dash="—"):
    if v is None:
        return dash
    return f"{v:,.{digits}f}"


def _aum(v) -> str:
    """순자산 표기 — 1조 이상은 조 단위."""
    if v is None:
        return "—"
    if v >= 10_000:
        return f"{v/10_000:,.1f}조"
    return f"{v:,.0f}억"


def _score_color(score: float, threshold: int = 60) -> str:
    if score >= 90:
        return "var(--good)"
    if score >= threshold:
        return "#5eb894"
    if score >= threshold * 0.75:
        return "var(--warn)"
    return "#7a8699"


def _dots(criteria: Dict) -> str:
    """8개 Trend Template 조건을 점으로 인코딩."""
    cells = "".join(
        f'<i class="dot{" on" if criteria.get(key) else ""}"></i>'
        for key, _ in CRITERIA_LABELS
    )
    passed = sum(1 for key, _ in CRITERIA_LABELS if criteria.get(key))
    return f'<div class="dots">{cells}<span class="cnt">{passed}/8</span></div>'


def _bar(score: float, max_score: int, threshold: int) -> str:
    pct = max(0.0, min(100.0, score / max_score * 100))
    mark = threshold / max_score * 100
    color = _score_color(score, threshold)
    return (
        f'<div class="bar">'
        f'<i style="width:{pct:.1f}%;background:{color}"></i>'
        f'<span class="mark" style="left:{mark:.1f}%"></span>'
        f'<span class="txt num">{score:.0f}</span>'
        f'</div>'
        f'<div class="barnote">/{max_score} · 매수선 {threshold}</div>'
    )


def _components(comp: Dict) -> str:
    rows = []
    for key, maximum in COMPONENT_MAX.items():
        val = comp.get(key, 0)
        pct = (val / maximum * 100) if maximum else 0
        rows.append(
            f'<div class="comp">'
            f'<span class="cn">{COMPONENT_LABELS[key]}</span>'
            f'<span class="cb"><i style="width:{pct:.0f}%"></i></span>'
            f'<span class="cv num">{val:g}<small style="color:var(--ink3)">/{maximum}</small></span>'
            f'</div>'
        )
    return "".join(rows)


def _criteria(criteria: Dict) -> str:
    rows = []
    for key, label in CRITERIA_LABELS:
        ok = bool(criteria.get(key))
        rows.append(
            f'<div class="crit {"ok" if ok else "no"}">'
            f'<span class="ck">{"✓" if ok else "✕"}</span>'
            f'<span>{_esc(label)}</span>'
            f'</div>'
        )
    return "".join(rows)


def _row(r: Dict, threshold: int, max_score: int) -> str:
    phase_label, phase_cls = PHASE_META.get(r["phase"], ("—", "p1"))
    buy_cls = " buy" if r["is_buy"] else ""

    # 펀드 정보
    turnover = r.get("turnover_eok")
    premium = r.get("premium_pct")
    fund = (
        '<div class="fund">'
        f'<div><div class="fl">순자산</div><div class="fv num">{_aum(r.get("aum_eok"))}</div></div>'
        f'<div><div class="fl">거래대금 20일 평균</div>'
        f'<div class="fv num">{f"{turnover:,.1f}억/일" if turnover is not None else "—"}</div></div>'
        f'<div><div class="fl">NAV 괴리율</div>'
        f'<div class="fv num">{f"{premium:+.2f}%" if premium is not None else "—"}</div></div>'
        '</div>'
    )

    # 매매 계획
    plan = (
        '<div class="plan">'
        f'<div><div class="pl">현재가</div><div class="pv num">{_won(r["current_price"])}</div></div>'
        f'<div><div class="pl">손절가</div><div class="pv stop num">{_won(r["stop_loss"])}</div></div>'
        f'<div><div class="pl">1차 익절</div><div class="pv mid num">{_won(r.get("mid_target"))}</div></div>'
        f'<div><div class="pl">최종 익절</div><div class="pv tgt num">{_won(r["target"])}</div></div>'
        '</div>'
    )

    if r["is_buy"]:
        verdict = '<div class="block pass">✅ 매수 적격 — Phase 2 · Trend Template 통과 · SEPA 임계값 충족</div>'
    else:
        verdict = f'<div class="block">⏸ 매수 보류 — {_esc(r["blocked_reason"])}</div>'

    reasons = "".join(f"<li>{_esc(x)}</li>" for x in r.get("reasons", []))

    extras = []
    if r.get("rs_slope") is not None:
        extras.append(f'RS 기울기 {r["rs_slope"]:+.3f}')
    if r.get("risk_reward_ratio"):
        extras.append(f'손익비 {r["risk_reward_ratio"]:.1f}:1')
    if r.get("gap_from_52w_high") is not None:
        extras.append(f'52주고가 대비 {r["gap_from_52w_high"]:+.1f}%')
    if r.get("is_vcp"):
        extras.append(f'VCP 품질 {r["vcp_quality"]:.0f}/100')
    if r.get("breakout"):
        extras.append(_esc(r["breakout"]))
    extras_html = (' · '.join(extras)) if extras else ''

    naver = f'https://finance.naver.com/item/main.naver?code={_esc(r["code"])}'

    return f"""
<details class="row{buy_cls}">
  <summary>
    <div class="cols">
      <div class="rank num">{r["rank"]}</div>
      <div class="tk">{_esc(r["name"])}<span class="nm num">{_esc(r["code"])}</span></div>
      <div class="sectwrap"><span class="sect">{_esc(r["category"])}</span></div>
      <div class="momwrap mom num">{_fmt(r["momentum_score"])}<small>모멘텀</small></div>
      <div class="phasewrap"><span class="phase {phase_cls}">P{r["phase"]} {phase_label}</span></div>
      <div class="dotswrap">{_dots(r["criteria_details"])}</div>
      <div class="barwrap">{_bar(r["sepa_score"], max_score, threshold)}</div>
      <div class="pxwrap px num">{_won(r["current_price"])}
        <small>손절 {_won(r["stop_loss"])}</small></div>
    </div>
  </summary>
  <div class="detail">
    {fund}
    {plan}
    <div class="dgrid">
      <div>
        <div class="dtitle">SEPA 점수 구성</div>
        {_components(r["components"])}
      </div>
      <div>
        <div class="dtitle">미너비니 트렌드 템플릿 {r["criteria_passed"]}/8</div>
        {_criteria(r["criteria_details"])}
      </div>
    </div>
    {f'<div class="dtitle" style="margin-top:16px">주요 지표</div><div style="font-size:12.5px;color:var(--ink2)">{extras_html}</div>' if extras_html else ''}
    <div class="dtitle" style="margin-top:16px">채점 근거</div>
    <ul class="why">{reasons}</ul>
    {verdict}
    <p style="margin-top:11px;font-size:12px">
      <a href="{naver}" target="_blank" rel="noopener noreferrer"
         style="color:var(--info);text-decoration:none">네이버 금융에서 보기 →</a></p>
  </div>
</details>"""


def build_html(data: Dict) -> str:
    """스캔 결과 dict → GitHub Pages용 완성 HTML."""
    results: List[Dict] = data["results"]
    threshold = data.get("buy_threshold", 60)
    max_score = data.get("max_score", 125)
    bm_label = data.get("benchmark_label", "KOSPI")

    total = len(results)
    buys = sum(1 for r in results if r["is_buy"])
    tmpl_pass = sum(1 for r in results if r["passes_template"])
    avg_sepa = (sum(r["sepa_score"] for r in results) / total) if total else 0
    phase2 = sum(1 for r in results if r["phase"] == 2)

    mk = data.get("market") or {}
    if mk:
        m_label, m_cls = PHASE_META.get(mk.get("phase"), ("—", "p1"))
        bm_card = f"""
    <div class="mcard bm">
      <div class="mlabel">시장 기준 · {_esc(bm_label)}</div>
      <div class="mval num">{_fmt(mk.get("price"))}</div>
      <div class="mnote"><span class="phase {m_cls}">P{mk.get("phase")} {m_label}</span>
        <span class="num">신뢰도 {mk.get("confidence", 0):.0f}% · 50일선 {mk.get("distance_from_50sma", 0):+.1f}%</span></div>
    </div>"""
    else:
        bm_card = (f'<div class="mcard bm"><div class="mlabel">시장 기준 · {_esc(bm_label)}</div>'
                   '<div class="mval">—</div></div>')

    w = data.get("momentum_weights", {})
    weight_str = " + ".join(f"{v}×{k}개월" for k, v in sorted(w.items(), key=lambda x: int(x[0])))

    uni = data.get("universe", {})

    # 네이버 조회 실패로 캐시를 썼다면 순자산·NAV가 최신이 아니라는 것을 밝힌다.
    if uni.get("source") == "cache":
        stale_note = (
            '<div class="exclu" style="background:#2a1414;border-color:#5a1e1e;color:#fca5a5">'
            f'⚠ 종목 정보 갱신 실패 — {_esc(uni.get("source_fetched_at") or "이전")} 스냅샷 사용 '
            '(순자산 · NAV 괴리율이 최신이 아닙니다. 시세는 정상)</div>'
        )
    else:
        stale_note = ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = "".join(_row(r, threshold, max_score) for r in results)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>국내 ETF 모멘텀 × SEPA 스크리너 | {_esc(data['scan_date'])}</title>
<meta name="description" content="레버리지·인버스를 제외한 국내 상장 ETF 가중 모멘텀 상위 {total}개의 미너비니 SEPA 스코어">
<style>{_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">KRX ETF · Momentum × SEPA</div>
    <h1>가중 모멘텀 상위 {total}개 ETF의 SEPA 점검</h1>
    <p class="sub">기준일 <b>{_esc(data['scan_date'])}</b> · 유니버스 <b>{data.get('universe_size', 0)}종목</b>
      · 모멘텀 가중치 <b>{_esc(weight_str)}</b></p>
    <div class="exclu">레버리지 · 인버스 {uni.get('excluded_leverage_inverse', 0)}종목 제외</div>
    {stale_note}
  </div>
</header>

<div class="wrap">

  <div class="market">
    {bm_card}
    <div class="mcard">
      <div class="mlabel">매수 적격</div>
      <div class="mval num" style="color:var(--good)">{buys}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">Phase 2 + 템플릿 + {threshold}점</div>
    </div>
    <div class="mcard">
      <div class="mlabel">템플릿 통과</div>
      <div class="mval num">{tmpl_pass}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">8개 조건 중 7개 이상</div>
    </div>
    <div class="mcard">
      <div class="mlabel">Phase 2</div>
      <div class="mval num">{phase2}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">확정 상승추세 국면</div>
    </div>
    <div class="mcard">
      <div class="mlabel">평균 SEPA</div>
      <div class="mval num">{avg_sepa:.0f}<small style="font-size:14px;color:var(--ink3)">/{max_score}</small></div>
      <div class="mnote">상위 {total}개 평균</div>
    </div>
  </div>

  <section class="sec">
    <div class="sec-head">
      <h2>모멘텀 랭킹 × SEPA 점수</h2>
      <span class="sec-note">행을 눌러 점수 구성과 8개 조건을 펼쳐 보세요</span>
    </div>

    <div class="cols colhead">
      <div>#</div><div>ETF</div><div>분류</div><div>모멘텀</div>
      <div>국면</div><div>템플릿</div><div>SEPA 점수</div><div style="text-align:right">현재가</div>
    </div>

    {rows}
  </section>

</div>

<footer>
  <div class="wrap">
    <p><b>유니버스</b> — 국내 상장 ETF 전 종목에서 레버리지·인버스를 제외하고,
       순자산 {uni.get('min_aum_eok', 0):,.0f}억원 · 20일 평균 거래대금 {uni.get('min_turnover_eok', 0):,.0f}억원 이상,
       상장 1년 이상(200거래일)인 상품만 남긴 <b>{data.get('universe_size', 0)}종목</b>입니다.</p>
    <p><b>랭킹 기준</b> — 가중 모멘텀 = {_esc(weight_str)} 수익률의 가중합. 매 거래일 전 종목을 재계산합니다.</p>
    <p><b>SEPA 점수</b> — 추세 40 · 펀드 품질 40 · 손익비 15 · 상대강도 10 · 거래량 10 · 진입 5 · VCP 5 (총 {max_score}점).
       마크 미너비니 <i>Trade Like a Stock Market Wizard</i>의 트렌드 템플릿과 SEPA 방법론 기반.</p>
    <p><b>펀드 품질 40점</b> — 개별주의 펀더멘털(매출·EPS·재고)은 ETF에 존재하지 않아, 같은 배점을
       순자산 규모 15 · 유동성 15 · NAV 괴리율 10으로 옮겼습니다. 나머지 85점은 원본과 동일합니다.</p>
    <p><b>매수 적격</b> — Phase 2 · 트렌드 템플릿 7/8 이상 · SEPA {threshold}점 이상을 모두 만족한 경우에만 표시됩니다.
       모멘텀 상위라도 대부분은 여기서 걸러집니다.</p>
    <p style="margin-top:12px">갱신 {now} · 데이터 네이버 금융(종목·순자산·NAV) / yfinance(시세)</p>
    <p style="color:#4a5568">본 페이지는 정보 제공 목적이며 투자 자문이 아닙니다. 과거 성과는 미래 수익을 보장하지 않습니다.</p>
  </div>
</footer>

</body>
</html>"""
