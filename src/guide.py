"""사용법 안내 페이지(docs/guide.html) 생성

스캔 결과와 무관한 정적 문서지만, 하드코딩 대신 config·sepa의 상수에서
숫자를 끌어와 만든다. 임계값이나 배점을 바꿨을 때 설명이 따로 놀지 않게
하기 위해서다. CSS도 report.py의 것을 그대로 물려받아 두 페이지의 모양이
어긋나지 않는다.

설명하는 규칙은 전부 이 저장소가 실제로 계산하는 것이다.
  - 진입 3관문      → sepa.score_sepa()의 blocked 판정
  - 손절가          → sepa.calculate_stop_loss()
  - 익절가·1차 익절 → sepa._score_risk_reward() 및 mid_target
"""

from typing import Dict

from .report import _CSS, _esc
from .sepa import CRITERIA_LABELS

_GUIDE_CSS = """
.guide{max-width:820px;margin:0 auto;padding:0 16px}
.guide h2{font-size:22px;font-weight:800;letter-spacing:-.02em;margin:44px 0 6px}
.guide h2 .no{
  display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;
  border-radius:8px;background:var(--accent);color:#1a1204;font-size:15px;margin-right:9px;
  vertical-align:2px
}
.guide h3{font-size:16px;font-weight:800;margin:26px 0 7px;color:var(--ink)}
.guide p{margin:9px 0;color:var(--ink2);font-size:14.5px;line-height:1.75;word-break:keep-all}
.guide p b,.guide li b{color:var(--ink);font-weight:700}
.guide ul,.guide ol{margin:9px 0 9px 20px;color:var(--ink2);font-size:14.5px;line-height:1.75}
.guide li{margin:5px 0;word-break:keep-all}
.lead{font-size:16px;color:var(--ink);line-height:1.7}

.callout{
  margin:16px 0;padding:14px 16px;border-radius:10px;font-size:14px;line-height:1.7;
  background:#17253d;border:1px solid #3b5680;color:var(--ink2);word-break:keep-all
}
.callout.warn{background:#2a1c14;border-color:#5a3a1e;color:#fcd34d}
.callout.stop{background:#2a1414;border-color:#5a1e1e;color:#fca5a5}
.callout b{color:var(--ink)}
.callout.warn b{color:#fde68a}
.callout.stop b{color:#fecaca}
.callout .ct{display:block;font-weight:800;margin-bottom:5px;font-size:14.5px}

/* 3개 관문 */
.gates{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin:18px 0}
.gate{
  background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:14px 15px
}
.gate .gn{font-size:10.5px;font-weight:800;letter-spacing:.1em;color:var(--accent)}
.gate .gt{font-size:15.5px;font-weight:800;margin:5px 0 6px}
.gate .gd{font-size:13px;color:var(--ink2);line-height:1.6;word-break:keep-all}
.gate-and{text-align:center;font-size:13px;color:var(--ink3);margin:-4px 0 14px;font-weight:700}

/* 청산 사다리 */
.ladder{margin:20px 0;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.rung{display:grid;grid-template-columns:104px 92px 1fr;gap:12px;align-items:center;
  padding:13px 15px;border-bottom:1px solid var(--line);font-size:14px}
.rung:last-child{border-bottom:none}
.rung .rl{font-weight:800;font-size:13.5px;white-space:nowrap}
.rung .rp{font-weight:800;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rung .ra{color:var(--ink2);font-size:13.5px;line-height:1.6;word-break:keep-all}
.rung.tgt{background:#122b21} .rung.tgt .rl,.rung.tgt .rp{color:var(--good)}
.rung.mid{background:#251f10} .rung.mid .rl,.rung.mid .rp{color:var(--warn)}
.rung.buy{background:var(--panel2)} .rung.buy .rl,.rung.buy .rp{color:var(--ink)}
.rung.stop{background:#2a1414} .rung.stop .rl,.rung.stop .rp{color:var(--bad)}

/* 계산 상자 */
.calc{
  margin:14px 0;padding:14px 16px;background:#0d1524;border:1px solid var(--line);
  border-radius:10px;font-size:14px;line-height:1.9;color:var(--ink2)
}
.calc .f{color:var(--info);font-weight:700;font-size:14.5px;display:block;margin-bottom:8px}
.calc .r{color:var(--ink);font-weight:800}

/* 체크리스트 */
.check{list-style:none;margin:14px 0 0 0;padding:0}
.check li{
  display:grid;grid-template-columns:26px 1fr;gap:10px;align-items:start;
  padding:10px 0;border-top:1px solid var(--line);font-size:14.5px;color:var(--ink2)
}
.check li:first-child{border-top:none}
.check .k{
  display:flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:6px;
  background:#22304a;color:#a9bdd9;font-size:12px;font-weight:800
}

/* 용어 */
.terms{margin:14px 0}
.term{
  border-top:1px solid var(--line);padding:13px 0;display:grid;
  grid-template-columns:170px 1fr;gap:16px;align-items:start
}
.term:first-child{border-top:none}
.term dt{font-weight:800;font-size:14.5px;color:var(--ink);word-break:keep-all}
.term dt small{display:block;font-weight:400;font-size:11.5px;color:var(--ink3);margin-top:2px}
.term dd{margin:0;font-size:14px;color:var(--ink2);line-height:1.7;word-break:keep-all}
.term dd em{font-style:normal;color:var(--warn)}

.tocwrap{
  margin:22px 0 6px;padding:15px 17px;background:var(--panel);border:1px solid var(--line);
  border-radius:11px
}
.tocwrap .tt{font-size:11px;font-weight:800;letter-spacing:.1em;color:var(--ink3);margin-bottom:9px}
.toc{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:7px 9px}
.toc li{margin:0}
.toc a{
  display:inline-block;padding:5px 11px;border-radius:7px;background:#1d2941;color:var(--ink2);
  text-decoration:none;font-size:13px;font-weight:600
}
.toc a:hover{background:#26324a;color:var(--ink)}

.backlink{display:inline-block;margin-top:10px;font-size:13px;color:var(--info);text-decoration:none}
.backlink:hover{text-decoration:underline}

@media (max-width:720px){
  .gates{grid-template-columns:1fr}
  .rung{grid-template-columns:88px 84px;gap:8px 10px}
  .rung .ra{grid-column:1/-1;margin-top:-2px}
  .term{grid-template-columns:1fr;gap:4px}
  .guide h2{font-size:19px}
}
"""


def _terms(rows) -> str:
    out = []
    for name, sub, desc in rows:
        sub_html = f"<small>{_esc(sub)}</small>" if sub else ""
        out.append(f'<div class="term"><dt>{_esc(name)}{sub_html}</dt><dd>{desc}</dd></div>')
    return f'<dl class="terms">{"".join(out)}</dl>'


def build_guide_html(cfg: Dict) -> str:
    """사용법 페이지 HTML. cfg는 run_daily가 config에서 뽑아 넘긴다."""
    thr = cfg["buy_threshold"]
    mx = cfg["max_score"]
    tmin = cfg["template_min"]
    bm = cfg["benchmark_label"]
    aum = cfg["min_aum_eok"]
    tov = cfg["min_turnover_eok"]
    link = cfg["link_label"]
    stop_mode = cfg.get("stop_mode", "swing")
    atr_mult = cfg.get("atr_mult", 3.0)
    atr_min = cfg.get("atr_min", 0.05) * 100
    atr_max = cfg.get("atr_max", 0.20) * 100
    need_52w = cfg.get("require_52w_low", False)

    # 예시용 가상 ETF — 실제 종목을 쓰면 특정 상품 추천처럼 읽히므로 일부러 지어낸 값이다.
    # 손절가는 현재 설정된 방식으로 계산한 값에 맞춘다.
    ex_buy = 20000
    ex_atr = 900                       # 하루 평균 변동폭 900원인 ETF 가정
    ex_stop = (ex_buy - int(atr_mult * ex_atr)) if stop_mode == "atr" else 18600
    ex_tgt = int(ex_buy * 1.30)
    ex_mid = (ex_buy + ex_tgt) // 2
    ex_risk = ex_buy - ex_stop
    ex_acct, ex_pct = 10_000_000, 1
    ex_budget = ex_acct * ex_pct // 100
    ex_qty = ex_budget // ex_risk
    ex_cost = ex_qty * ex_buy

    gate2_extra = ("" if not need_52w else
                   " 그중 <b>‘52주 저가 대비 +30% 이상’은 반드시</b> 통과해야 합니다.")

    c6_note = ("" if not need_52w else
               "그리고 <b>6번 ‘52주 저가 대비 +30% 이상’은 개수와 상관없이 반드시</b> "
               "통과해야 합니다 — 8개 중 유일하게 <b>‘이 상품이 실제로 움직이는가’</b>를 "
               "묻는 조건이라, 이게 빠지면 채권처럼 거의 움직이지 않는 상품이 "
               "관문을 통과해 버립니다.")

    if stop_mode == "atr":
        stop_explain = f"""<ul>
    <li>그 ETF가 <b>하루에 실제로 얼마나 움직이는지</b>(ATR)를 먼저 잽니다.
      최근 14일 동안의 하루 등락폭 평균이라고 보면 됩니다.</li>
    <li>손절가 = <b>현재가 − (하루 평균 등락폭 × {atr_mult:g})</b>.
      크게 출렁이는 ETF는 손절가를 멀리, 얌전한 ETF는 가까이 둡니다.
      <b>종목마다 손절폭이 다릅니다.</b></li>
    <li>그렇게 나온 값이 현재가에서 <b>{atr_min:.0f}%보다 가까우면 {atr_min:.0f}%로</b>,
      <b>{atr_max:.0f}%보다 멀면 {atr_max:.0f}%로</b> 맞춥니다.</li>
  </ul>
  <div class="callout">
    <span class="ct">왜 이렇게 바꿨나</span>
    원래는 모든 종목에 <b>3~10%</b>를 똑같이 적용했습니다. 그런데 과거 데이터로 검증해 보니
    <b>손절된 거래의 71%가 6개월 안에 원래 매수가를 회복</b>했습니다. 위험을 막은 게 아니라
    <b>잔파도에 흔들려 나온 것</b>입니다. ETF마다 움직이는 폭이 다른데 같은 자를 댄 게
    원인이었습니다. <a href="./backtest.html#" style="color:#9ec5f5">백테스트 결과 보기 →</a>
  </div>"""
    else:
        stop_explain = """<ul>
    <li><b>최근 10일 중 가장 낮았던 가격</b>보다 살짝 아래, 또는 <b>50일선</b> 바로 아래 —
      <b>둘 중 더 높은 쪽</b>을 씁니다. 최근 바닥이 깨지면 상승이 끝났다고 보는 것입니다.</li>
    <li>그렇게 나온 값이 현재가에서 <b>3%보다 가까우면 3%로</b>, <b>10%보다 멀면 10%로</b> 맞춥니다.</li>
  </ul>"""

    criteria_list = "".join(
        f"<li>{_esc(label)}</li>" for _, label in CRITERIA_LABELS
    )

    term_rows_screen = [
        ("ETF", "상장지수펀드",
         "여러 종목을 한 바구니에 담아 놓고, 그 바구니를 주식처럼 사고팔 수 있게 만든 상품입니다. "
         "'반도체 ETF'를 사면 반도체 회사 수십 개를 한 번에 조금씩 사는 셈입니다. "
         "한 회사가 망해도 타격이 작다는 게 개별 주식과 다른 점입니다."),
        ("레버리지 · 인버스", "이 사이트에서 제외한 상품",
         "레버리지는 오르내림을 2배로 뻥튀기한 상품, 인버스는 <em>내리면 버는</em> 상품입니다. "
         "둘 다 하루 단위로 계산이 다시 시작돼서, 오래 들고 있으면 지수가 제자리로 와도 "
         "내 돈은 줄어 있습니다. 이 사이트의 규칙과 맞지 않아 아예 목록에서 뺐습니다."),
        ("가중 모멘텀", "랭킹 순서를 정하는 값",
         "최근에 얼마나 많이 올랐는지를 하나의 숫자로 만든 것입니다. "
         f"{_esc(cfg['weight_str'])}의 수익률을 더하되 <b>최근 1개월에 가장 큰 비중</b>을 둡니다. "
         "숫자가 클수록 요즘 세게 오르고 있다는 뜻이지, 좋은 상품이라는 뜻이 아닙니다."),
        ("분류", "행에 붙은 회색 딱지",
         "이 ETF가 무엇을 담고 있는지입니다. 국내지수 · 업종·테마 · 해외주식 · 원자재 · 채권 · 기타. "
         "<b>상위 20개가 전부 같은 분류면 주의하세요.</b> 예를 들어 전부 '반도체'라면 "
         "20개를 나눠 사도 사실상 한 곳에 몰아넣은 것과 같습니다."),
        ("국면 (Phase)", "P1 · P2 · P3 · P4",
         "주가가 지금 어느 단계에 있는지를 4단계로 나눈 것입니다. "
         "<b>P1 베이스</b> = 옆으로 기며 힘을 모으는 중. "
         "<b>P2 상승추세</b> = 확실히 오르는 중. "
         "<b>P3 분산·과열</b> = 너무 많이 올라 꼭대기 기운. "
         "<b>P4 하락추세</b> = 내리는 중. 이 방법은 <b>P2에서만 삽니다.</b>"),
        ("신뢰도", "국면 옆 %",
         "국면 판정이 얼마나 뚜렷한지입니다. 조건에 딱 들어맞을수록 높아집니다. "
         "낮다고 틀린 건 아니고, '애매한 구간'이라는 뜻입니다."),
        ("트렌드 템플릿", "8칸짜리 네모",
         f"미너비니가 정한 8개 조건입니다. 통과한 칸이 초록으로 찹니다. "
         f"<b>{tmin}칸 이상</b>이어야 매수 후보가 됩니다. 8개 조건은 아래에 따로 적었습니다."),
        ("SEPA 점수", f"{mx}점 만점 막대",
         f"7개 항목을 합친 종합 점수입니다. 막대 위 <b>세로선이 {thr}점</b>이고, "
         f"이 선을 넘어야 매수 후보가 됩니다. 점수가 높다고 더 많이 오른다는 뜻은 아닙니다. "
         f"<b>규칙을 얼마나 잘 지켰는지</b>를 재는 자입니다."),
        ("초록 테두리 행", "매수 적격",
         "세 관문을 모두 통과한 행입니다. 회색 행은 하나 이상 걸린 것이고, "
         "펼치면 맨 아래에 무엇 때문에 걸렸는지 적혀 있습니다."),
    ]

    term_rows_detail = [
        ("순자산", "펀드 크기",
         f"이 ETF에 모인 돈의 총액입니다. 작으면 운용사가 상품을 접을 수 있습니다(상장폐지). "
         f"이 사이트는 <b>{aum:,.0f}억원</b> 미만은 아예 목록에서 뺍니다."),
        ("거래대금", "하루에 오간 돈",
         f"20일 평균으로 하루에 얼마어치가 거래되는지입니다. 적으면 <b>내가 팔고 싶을 때 "
         f"제값에 못 팝니다.</b> 이 사이트는 하루 평균 <b>{tov:,.0f}억원</b> 미만을 뺍니다."),
        ("NAV 괴리율", "제값과의 차이",
         "NAV는 ETF가 담고 있는 것들의 <b>진짜 값어치</b>입니다. 괴리율은 시장 가격이 그보다 "
         "얼마나 비싸게(+) 또는 싸게(−) 거래되는지입니다. +1%면 100원짜리를 101원에 사는 셈이라, "
         "0%에 가까울수록 좋습니다."),
        ("현재가 · 손절가 · 1차 익절 · 최종 익절", "매매 계획 4칸",
         "이 페이지가 계산해 주는 네 개의 가격입니다. 사는 값, 실패를 인정하고 나오는 값, "
         "절반 파는 값, 나머지를 파는 값. 쓰는 법은 위의 <b>2번 · 3번</b>에 있습니다."),
        ("추세 구조", "40점",
         "이동평균선보다 얼마나 위에 있고, 그 선들이 얼마나 가파르게 오르는지입니다. "
         "너무 많이 오른 경우(50일선보다 20% 이상 위)에는 <b>오히려 점수를 깎습니다.</b> "
         "늦게 뛰어드는 것을 막기 위해서입니다."),
        ("펀드 품질", "40점",
         "상품 자체가 멀쩡한지입니다. 순자산 · 거래대금 · 괴리율을 봅니다. "
         "개별 주식이라면 회사의 매출과 이익을 볼 자리인데, ETF에는 그런 게 없어 이걸로 대신합니다."),
        ("손익비", "15점",
         "<b>벌 수 있는 폭 ÷ 잃을 수 있는 폭</b>입니다. 3:1이면 성공하면 3만원 벌고 "
         "실패하면 1만원 잃는 자리라는 뜻입니다. <b>2:1이 안 되면 0점</b>입니다. "
         "절반만 맞혀도 남는 자리에서만 사겠다는 뜻입니다."),
        ("상대강도 · RS 기울기", "10점",
         f"{bm} 지수보다 잘 가고 있는지입니다. 값이 <b>양수면 시장을 이기는 중</b>, "
         f"음수면 시장보다 못 가는 중입니다. 시장이 오를 때 같이 오르는 정도로는 부족하고, "
         f"더 빨리 올라야 좋은 점수를 받습니다."),
        ("거래량", "10점",
         "오른 날의 거래량과 내린 날의 거래량을 비교합니다. 오를 때 사람이 몰리면 좋은 신호고, "
         "내릴 때 몰리면 빠져나가는 중이라 나쁜 신호입니다."),
        ("진입 품질", "5점",
         "지금 사기에 적당한 자리인지입니다. 1년 최고가에 가까울수록 높습니다. "
         "이상하게 들리겠지만, 이 방법은 <b>싼 것을 사는 게 아니라 강한 것을 삽니다.</b>"),
        ("VCP", "5점 · 변동성 수축 패턴",
         "오르다 잠깐 쉬고, 또 오르다 <b>아까보다 더 조금만 쉬고</b>를 2~6번 반복한 모양입니다. "
         "쉬는 폭이 점점 좁아지는 건 팔 사람이 거의 다 팔았다는 뜻이라, 미너비니가 가장 좋아하는 "
         "모양입니다. 있으면 보너스, 없어도 감점은 아닙니다."),
        ("돌파", "상세의 주요 지표",
         "그동안 못 넘던 가격대를 뚫고 올라간 것입니다. <b>거래량 확인</b>이 붙어 있으면 "
         "평소보다 1.5배 넘는 거래량을 동반한 돌파라 더 믿을 만합니다."),
        ("52주 고가 · 저가", "1년 최고·최저",
         "최근 1년 동안의 가장 비쌌던 값과 가장 쌌던 값입니다. 지금 가격이 그 사이 어디쯤인지가 "
         "트렌드 템플릿의 두 조건에 쓰입니다."),
        ("이동평균선", "50일선 · 150일선 · 200일선",
         "최근 50일(또는 150일, 200일) 종가의 평균을 이어 그린 선입니다. "
         "<b>주가가 이 선 위에 있으면 최근 산 사람들이 대체로 이익</b>이라는 뜻이고, "
         "그래서 잘 안 무너집니다. 짧은 선이 긴 선 위에 있으면 상승 중이라는 신호입니다."),
    ]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>사용법 | 국내 ETF 모멘텀 × SEPA 스크리너</title>
<meta name="description" content="스크리너의 숫자를 읽고 매수·매도 규칙을 실행하는 법을 처음부터 설명합니다.">
<style>{_CSS}{_GUIDE_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">사용법</div>
    <h1>언제 사고, 언제 파는가</h1>
    <p class="sub">이 사이트의 숫자를 읽고 그대로 실행하는 법 · 처음 보는 사람 기준</p>
    <a class="backlink" href="./index.html">← 스크리너로 돌아가기</a>
  </div>
</header>

<div class="guide">

  <div class="tocwrap">
    <div class="tt">목차</div>
    <ul class="toc">
      <li><a href="#what">0. 이게 뭔가</a></li>
      <li><a href="#buy">1. 언제 사는가</a></li>
      <li><a href="#size">2. 얼마나 사는가</a></li>
      <li><a href="#sell">3. 언제 파는가</a></li>
      <li><a href="#routine">4. 하루 루틴</a></li>
      <li><a href="#mistakes">5. 흔한 실수</a></li>
      <li><a href="#terms">6. 용어 사전</a></li>
    </ul>
  </div>

  <h2 id="what"><span class="no">0</span>이게 뭔가</h2>

  <p class="lead">이 사이트는 매일 저녁, 한국에 상장된 ETF 400여 개를 자동으로 훑어서
    <b>최근 가장 세게 오른 20개</b>를 뽑고, 그 20개가 <b>사도 되는 상태인지</b>를 점수로 매깁니다.</p>

  <p>규칙은 제가 지어낸 것이 아니라 <b>마크 미너비니</b>라는 미국 투자자가 책에 쓴 방법을
    그대로 코드로 옮긴 것입니다. 사람의 판단이 들어가지 않고, 매일 같은 자로 잽니다.</p>

  <div class="callout">
    <span class="ct">가장 중요한 오해 하나</span>
    <b>1위라고 사라는 뜻이 아닙니다.</b> 1위는 그냥 '가장 많이 올랐다'는 뜻입니다.
    실제로 상위 20개 중 대부분은 규칙에서 탈락합니다. 이 사이트의 진짜 목적은
    <b>왜 탈락했는지를 보여주는 것</b>입니다. 초록 테두리가 쳐진 행만 규칙을 통과한 것입니다.
  </div>

  <h2 id="buy"><span class="no">1</span>언제 사는가 — 3개의 관문</h2>

  <p>사도 되는 상태인지는 <b>세 가지를 모두</b> 통과해야 합니다. 하나라도 걸리면 사지 않습니다.
    화면에서는 이 셋을 통과한 행에만 <b>초록 테두리</b>가 쳐집니다.</p>

  <div class="gates">
    <div class="gate">
      <div class="gn">관문 1</div>
      <div class="gt">국면이 P2</div>
      <div class="gd">지금 <b>확실히 오르는 중</b>이어야 합니다.
        바닥에서 반등을 노리거나, 떨어지는 걸 주워 담지 않습니다.</div>
    </div>
    <div class="gate">
      <div class="gn">관문 2</div>
      <div class="gt">템플릿 {tmin}칸 이상</div>
      <div class="gd">8개 조건 중 <b>{tmin}개 이상</b> 통과.
        오르는 게 잠깐이 아니라 <b>구조가 튼튼한지</b>를 봅니다.{gate2_extra}</div>
    </div>
    <div class="gate">
      <div class="gn">관문 3</div>
      <div class="gt">SEPA {thr}점 이상</div>
      <div class="gd">{mx}점 만점 중 <b>{thr}점</b> 이상.
        지금 사기에 적당한 값인지, 상품 자체는 멀쩡한지를 봅니다.</div>
    </div>
  </div>
  <div class="gate-and">세 개 모두 통과 = 매수 적격 (초록 테두리)</div>

  <h3>왜 세 개나 보나요?</h3>
  <p>하나만 보면 속기 때문입니다. 각각이 <b>서로 다른 것</b>을 봅니다.</p>
  <ul>
    <li><b>국면</b>은 "지금 오르고 있나?"를 봅니다. 오르지 않는 걸 사면 언제 오를지 알 수 없습니다.</li>
    <li><b>템플릿</b>은 "그 오름세가 튼튼한가?"를 봅니다. 하루 반짝 오른 것과 반년째 오르는 것은 다릅니다.</li>
    <li><b>SEPA 점수</b>는 "지금 이 값에 사도 되나, 이 상품 자체는 괜찮나?"를 봅니다.
      너무 많이 올라버린 자리는 점수가 깎이고, 거래가 없는 상품도 점수가 낮습니다.</li>
  </ul>

  <h3>탈락한 이유 읽는 법</h3>
  <p>회색 행을 눌러 펼치면 맨 아래에 <b>⏸ 매수 보류</b>와 함께 이유가 한 줄 적혀 있습니다.
    셋 중 <b>먼저 걸린 것 하나만</b> 보여줍니다.</p>
  <ul>
    <li><b>"Phase 1 (미너비니는 Phase 2만 매수)"</b> — 아직 오르는 중이 아닙니다. 기다립니다.</li>
    <li><b>"Trend Template 5/8"</b> — 오르고는 있는데 구조가 아직 덜 갖춰졌습니다.</li>
    <li><b>"SEPA 54점 (임계값 {thr} 미달)"</b> — 앞의 둘은 통과했는데 점수가 모자랍니다.</li>
  </ul>

  <div class="callout warn">
    <span class="ct">매수 적격이 0개인 날이 자주 있습니다</span>
    그럴 때 <b>가장 점수 높은 걸 대신 사는 것</b>이 이 방법을 망치는 가장 흔한 길입니다.
    0개면 그날은 안 사는 게 규칙입니다. 시장 전체가 나쁠 때는 몇 주 내내 0개일 수도 있습니다.
    <b>안 사는 것도 실행입니다.</b>
  </div>

  <h2 id="size"><span class="no">2</span>얼마나 사는가</h2>

  <p>살 종목을 정했으면 <b>몇 주를 살지</b>를 정해야 합니다. 이걸 감으로 정하면
    한 번의 실패로 계좌가 크게 흔들립니다. 미너비니의 방식은 거꾸로 계산합니다.
    <b>"이번에 틀리면 얼마까지 잃어도 되는가"를 먼저 정하고, 거기서 수량을 역산합니다.</b></p>

  <div class="calc">
    <span class="f">살 수량 = (내 전체 투자금 × 감수할 비율) ÷ (현재가 − 손절가)</span>
    예를 들어 전체 투자금이 <b>{ex_acct:,}원</b>이고, 한 번 틀릴 때
    <b>{ex_pct}%</b>인 <b>{ex_budget:,}원</b>까지만 잃겠다고 정했다고 합시다.<br>
    이 페이지가 알려준 값이 현재가 <b>{ex_buy:,}원</b>, 손절가 <b>{ex_stop:,}원</b>이라면
    한 주당 잃을 수 있는 돈은 <b>{ex_risk:,}원</b>입니다.<br>
    → {ex_budget:,} ÷ {ex_risk:,} = <span class="r">{ex_qty}주</span>
    (사는 데 드는 돈은 {ex_qty} × {ex_buy:,} = <b>{ex_cost:,}원</b>)
  </div>

  <p>여기서 중요한 점: <b>손절가가 멀수록 적게 사게 됩니다.</b> 위험한 자리일수록 저절로
    조금만 사게 되는 구조입니다. 반대로 손절가가 가까우면 더 많이 살 수 있습니다.</p>

  <div class="callout">
    <span class="ct">감수할 비율은 이 페이지가 정해주지 않습니다</span>
    미너비니는 한 종목에 <b>전체의 1~2% 정도</b>만 걸라고 씁니다. 10번 연속 틀려도
    계좌의 10~20%만 잃는다는 계산입니다. 다만 이건 각자의 사정에 달린 문제라
    이 사이트가 대신 정해줄 수 없습니다. <b>처음이라면 작게 시작하세요.</b>
  </div>

  <h2 id="sell"><span class="no">3</span>언제 파는가 — 3개의 출구</h2>

  <p class="lead">파는 계획은 <b>사기 전에</b> 정해둡니다. 사고 나서 정하려고 하면
    이미 감정이 섞여서 못 팝니다. 행을 펼치면 나오는 <b>매매 계획 4칸</b>이 바로 이 계획입니다.</p>

  <p>현재가 {ex_buy:,}원인 가상의 ETF를 예로 들면 이렇게 생겼습니다.</p>

  <div class="ladder">
    <div class="rung tgt">
      <span class="rl">최종 익절</span>
      <span class="rp">{ex_tgt:,}원</span>
      <span class="ra">여기 닿으면 <b>남은 전부를 판다.</b> 매수가보다 30% 위입니다.</span>
    </div>
    <div class="rung mid">
      <span class="rl">1차 익절</span>
      <span class="rp">{ex_mid:,}원</span>
      <span class="ra">여기 닿으면 <b>절반만 판다.</b> 그리고 손절가를 매수가({ex_buy:,}원)로 올린다.</span>
    </div>
    <div class="rung buy">
      <span class="rl">현재가 (매수)</span>
      <span class="rp">{ex_buy:,}원</span>
      <span class="ra">여기서 삽니다.</span>
    </div>
    <div class="rung stop">
      <span class="rl">손절가</span>
      <span class="rp">{ex_stop:,}원</span>
      <span class="ra">여기 닿으면 <b>전부 판다. 예외 없음.</b> 매수가보다 {(ex_buy-ex_stop)/ex_buy*100:.0f}% 아래입니다.</span>
    </div>
  </div>

  <h3>출구 1 — 손절가에 닿으면 전부 판다</h3>
  <p>가장 중요한 규칙이고, 가장 지키기 어려운 규칙입니다. 손절가는 <b>"내 판단이 틀렸다"고
    시장이 알려주는 가격</b>입니다. 여기서 '조금만 더 기다려보자'가 시작되면
    이 방법 전체가 무너집니다.</p>
  <p>이 페이지의 손절가는 이렇게 계산됩니다:</p>
  {stop_explain}

  <h3>출구 2 — 1차 익절에서 절반 팔고, 손절가를 매수가로 올린다</h3>
  <p>1차 익절은 <b>현재가와 최종 익절의 딱 중간</b>입니다. 여기서 절반을 팔면
    <b>이미 번 돈은 확보</b>됩니다. 그리고 남은 절반의 손절가를 <b>내가 산 가격</b>으로 올립니다.</p>
  <div class="callout">
    <span class="ct">이 한 가지가 왜 중요한가</span>
    손절가를 매수가로 올리는 순간, 이 거래에서 <b>최악의 결과가 "본전"</b>이 됩니다.
    더 오르면 더 벌고, 떨어져도 잃지 않습니다. 마음이 편해지니 남은 절반을
    <b>끝까지 들고 갈 수 있게</b> 됩니다. 크게 버는 거래는 여기서 나옵니다.
  </div>

  <h3>출구 3 — 최종 익절에서 나머지를 판다</h3>
  <p>최종 익절은 매수가보다 <b>30% 위</b>입니다(P2 기준). 여기 닿으면 나머지를 정리합니다.
    "더 오를 것 같은데" 싶어도 계획대로 파는 것이, 정해둔 규칙을 지키는 연습입니다.</p>

  <div class="callout warn">
    <span class="ct">가격은 매일 다시 계산됩니다</span>
    이 사이트의 손절가·익절가는 <b>오늘 사는 사람 기준</b>으로 매일 새로 계산된 값입니다.
    내가 어제 산 가격을 기억하지 못합니다. <b>한 번 사면 그날의 네 숫자를 따로 적어두고,
    그 숫자로 끝까지 관리하세요.</b> 다음 날 페이지가 바뀌었다고 계획을 바꾸면 안 됩니다.
  </div>

  <h2 id="routine"><span class="no">4</span>하루 루틴</h2>

  <p>평일 오후 5시에 갱신됩니다. 매일 5분이면 충분합니다.</p>

  <ol class="check">
    <li><span class="k">1</span><span><b>이미 갖고 있는 것부터 확인합니다.</b>
      적어둔 손절가·익절가에 닿았는지 봅니다. 닿았으면 그대로 실행합니다.
      이게 새로 살 것을 찾는 것보다 먼저입니다.</span></li>
    <li><span class="k">2</span><span><b>맨 위 요약 바에서 {bm} 국면을 봅니다.</b>
      시장 전체가 P4(하락추세)면 개별 ETF가 좋아 보여도 성공률이 떨어집니다.
      이럴 땐 수량을 줄이거나 쉬는 것도 방법입니다.</span></li>
    <li><span class="k">3</span><span><b>초록 테두리 행이 있는지 봅니다.</b>
      없으면 오늘은 끝입니다. 있으면 다음으로 갑니다.</span></li>
    <li><span class="k">4</span><span><b>그 행을 펼쳐 봅니다.</b>
      거래대금이 너무 적지 않은지, 괴리율이 크지 않은지, 이미 갖고 있는 것과
      <b>같은 분류가 아닌지</b> 확인합니다.</span></li>
    <li><span class="k">5</span><span><b>수량을 계산하고, 네 개의 가격을 적어둡니다.</b>
      현재가 · 손절가 · 1차 익절 · 최종 익절. 적지 않으면 지킬 수 없습니다.</span></li>
  </ol>

  <p style="margin-top:14px">ETF 이름을 누르면 {_esc(link)}의 해당 종목 페이지가 새 탭에서 열립니다.
    실제 주문은 거기서 하게 됩니다.</p>

  <h2 id="mistakes"><span class="no">5</span>흔한 실수</h2>

  <ul>
    <li><b>매수 적격이 없는데 아쉬워서 산다</b> — 가장 흔하고 가장 비쌉니다.
      0개인 날은 쉬라는 뜻입니다.</li>
    <li><b>손절가에서 안 판다</b> — "곧 돌아올 거야"는 계획이 아닙니다.
      손절 한 번을 미루면 그동안의 이익을 다 토해냅니다.</li>
    <li><b>비슷한 걸 여러 개 산다</b> — 반도체 ETF 3개는 <b>분산이 아닙니다.</b>
      분류 딱지를 보고 겹치지 않게 고르세요.</li>
    <li><b>모멘텀 1위만 본다</b> — 1위는 가장 많이 오른 것일 뿐입니다.
      초록 테두리가 없으면 규칙상 사지 않는 자리입니다.</li>
    <li><b>한 번에 크게 산다</b> — 수량은 손절폭에서 역산하는 것이지,
      확신의 크기로 정하는 게 아닙니다.</li>
    <li><b>매일 계획을 바꾼다</b> — 살 때 적어둔 네 숫자로 끝까지 갑니다.</li>
  </ul>

  <h2 id="terms"><span class="no">6</span>용어 사전</h2>

  <h3>화면에서 바로 보이는 것</h3>
  {_terms(term_rows_screen)}

  <h3>트렌드 템플릿 8개 조건</h3>
  <p>펼친 상세의 오른쪽에 체크리스트로 나옵니다. ✓가 {tmin}개 이상이어야 관문 2를 통과합니다.
    {c6_note}
    큰 흐름은 <b>"짧은 평균선이 긴 평균선 위에 있고, 주가는 그보다 더 위에 있고,
    1년 최고가 근처에 있다"</b>는 하나의 그림입니다.</p>
  <ol>{criteria_list}</ol>

  <h3>펼쳤을 때 나오는 것</h3>
  {_terms(term_rows_detail)}

  <div class="callout stop" style="margin-top:34px">
    <span class="ct">꼭 읽어주세요</span>
    이 페이지는 <b>계산 결과를 읽는 법</b>을 설명한 것이지, 투자 권유가 아닙니다.
    저는 여러분의 사정을 알지 못하고, 어떤 종목도 추천하지 않습니다.
    이 규칙을 그대로 지켜도 <b>손실이 날 수 있고, 실제로 자주 납니다.</b>
    미너비니 방식도 절반 가까이는 손절로 끝나며, 크게 버는 소수의 거래로 전체를 남기는 방법입니다.
    잃어도 생활에 지장이 없는 돈으로만, 처음에는 아주 작게 시작하세요.
  </div>

  <div class="callout warn" style="margin-top:26px">
    <span class="ct">이 규칙을 과거에 적용하면 어땠을까</span>
    2019년부터 실제 데이터로 돌려 봤습니다. 결과는 좋지 않았고, 그 이유까지 정리했습니다.
    <b>돈을 넣기 전에 꼭 읽어보세요.</b><br>
    <a href="./backtest.html" style="color:#fde68a;font-weight:700">백테스트 결과 보기 →</a>
  </div>

  <p style="margin-top:22px"><a class="backlink" href="./index.html">← 스크리너로 돌아가기</a></p>

</div>

<footer>
  <div class="wrap">
    <p><b>방법론</b> — Mark Minervini, <i>Trade Like a Stock Market Wizard</i>의
       트렌드 템플릿과 SEPA. 이 사이트는 그 규칙을 코드로 옮긴 것입니다.</p>
    <p style="color:#4a5568">본 페이지는 정보 제공 목적이며 투자 자문이 아닙니다.
       과거 성과는 미래 수익을 보장하지 않습니다.</p>
  </div>
</footer>

</body>
</html>"""
