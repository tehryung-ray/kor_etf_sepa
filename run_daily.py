"""국내 ETF 가중모멘텀 × SEPA 스크리너 — 일일 실행 엔트리포인트

흐름:
  1. 네이버 금융에서 국내 상장 ETF 전 종목 수집 → 레버리지·인버스 제외
  2. 순자산 하한을 넘는 후보의 2년 일봉 배치 다운로드 (yfinance, `.KS`)
  3. 20일 평균 거래대금 하한으로 한 번 더 정제
  4. 가중 모멘텀 점수 산출 → 상위 N개 선정
  5. 상위 N개에 대해 Phase 분류 · VCP · 펀드 품질 → SEPA 점수 채점
  6. JSON 저장 + GitHub Pages용 HTML 생성

사용:
  python run_daily.py                  # 기본 (config.TOP_N)
  python run_daily.py --top 30         # 상위 30개
  python run_daily.py --include-leverage   # 레버리지·인버스 포함 (기본은 제외)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np

# Windows 콘솔 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import config
from src.universe import (
    get_etf_list,
    download_prices,
    filter_by_turnover,
    get_price_matrix,
    avg_turnover_eok,
)
from src.momentum import calc_momentum_score, rank_latest
from src.phase_indicators import (
    classify_phase,
    calculate_relative_strength,
    detect_vcp_pattern,
)
from src.sepa import score_sepa
from src.etf_quality import build_quality
from src.report import build_html
from src.guide import build_guide_html

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)

LINK_LABELS = {"toss": "토스증권", "naver": "네이버 금융"}


def _json_safe(obj):
    """numpy 스칼라·Timestamp를 파이썬 기본 타입으로 변환 (json.dumps default)."""
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        val = float(obj)
        return None if np.isnan(val) else val
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):          # pandas.Timestamp
        return obj.isoformat()
    raise TypeError(f"직렬화 불가 타입: {type(obj).__name__}")


def analyze_market(prices: dict, benchmark: str, label: str) -> dict:
    """벤치마크(KOSPI)의 현재 국면을 요약한다."""
    bm = prices.get(benchmark)
    if bm is None or len(bm) < 200:
        return {}

    price = float(bm["Close"].iloc[-1])
    info = classify_phase(bm, price)
    return {
        "ticker": benchmark,
        "label": label,
        "price": round(price, 2),
        "phase": info.get("phase"),
        "phase_name": info.get("phase_name"),
        "confidence": info.get("confidence"),
        "sma_50": info.get("sma_50"),
        "sma_200": info.get("sma_200"),
        "distance_from_50sma": info.get("distance_from_50sma"),
    }


def run(top_n: int, exclude_leverage: bool = True) -> dict:
    # ── 1) 유니버스 ──────────────────────────────────────────────────
    etfs, uni_stats = get_etf_list(
        cache_path=str(ROOT / config.UNIVERSE_CACHE),
        exclude_leverage_inverse=exclude_leverage,
        min_aum_eok=config.MIN_AUM_EOK,
        min_price=config.MIN_PRICE,
    )
    meta = etfs.set_index("code").to_dict(orient="index")
    codes = etfs["code"].tolist()

    prices = download_prices(codes, years=config.PRICE_YEARS,
                             benchmark=config.BENCHMARK)
    prices = filter_by_turnover(prices, config.MIN_TURNOVER_EOK,
                                exclude=[config.BENCHMARK])

    close = get_price_matrix(prices)
    log.info("가격 매트릭스: %d일 × %d종목", *close.shape)

    # ── 2) 가중 모멘텀 랭킹 ──────────────────────────────────────────
    mom = calc_momentum_score(close, config.MOMENTUM_WEIGHTS,
                              config.SKIP_RECENT_MONTH)
    ranking = rank_latest(mom, exclude=[config.BENCHMARK], top_n=top_n)
    log.info("모멘텀 상위 %d개 선정: %s", top_n,
             ", ".join(meta.get(r["ticker"], {}).get("name", r["ticker"])
                       for r in ranking[:8]) + " ...")

    # ── 3) SEPA 채점 ─────────────────────────────────────────────────
    bm_close = close[config.BENCHMARK] if config.BENCHMARK in close.columns else None
    results = []

    for entry in ranking:
        code = entry["ticker"]
        pdata = prices.get(code)
        row = meta.get(code, {})
        if pdata is None or len(pdata) < 200:
            log.warning("%s: 데이터 부족, 건너뜀", code)
            continue

        try:
            current_price = float(pdata["Close"].iloc[-1])
            phase_info = classify_phase(pdata, current_price)

            if phase_info.get("phase", 0) == 0:
                log.warning("%s: Phase 분류 불가, 건너뜀", code)
                continue

            rs_series = (calculate_relative_strength(pdata["Close"], bm_close)
                         if bm_close is not None else None)
            vcp = detect_vcp_pattern(pdata, current_price, phase_info)

            quality = build_quality({**row, "code": code},
                                    avg_turnover_eok(pdata))

            sepa = score_sepa(
                code=code,
                price_data=pdata,
                current_price=current_price,
                phase_info=phase_info,
                rs_series=rs_series,
                quality=quality,
                vcp_data=vcp,
                template_pass_min=config.TEMPLATE_PASS_MIN,
                buy_threshold=config.SEPA_BUY_THRESHOLD,
                fund_quality_mode=config.FUND_QUALITY_MODE,
                benchmark_label=config.BENCHMARK_LABEL,
            )

            sepa.update({
                "rank": entry["rank"],
                "momentum_score": entry["momentum_score"],
                "name": row.get("name", code),
                "category": row.get("category", "기타"),
            })
            results.append(sepa)

            log.info("  #%-2d %-6s %-28s 모멘텀 %6.2f | Phase %d | Template %d/8 | SEPA %5.1f%s",
                     entry["rank"], code, row.get("name", "")[:28],
                     entry["momentum_score"], sepa["phase"],
                     sepa["criteria_passed"], sepa["sepa_score"],
                     "  ✅매수" if sepa["is_buy"] else "")

        except Exception as e:
            log.error("%s 분석 실패: %s", code, e)
            continue

    scan_date = close.index[-1].strftime("%Y-%m-%d")
    universe_size = len([c for c in prices if c != config.BENCHMARK])

    return {
        "scan_date": scan_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe_size": universe_size,
        "top_n": top_n,
        "momentum_weights": config.MOMENTUM_WEIGHTS,
        "buy_threshold": config.SEPA_BUY_THRESHOLD,
        "max_score": config.SEPA_MAX_SCORE,
        "benchmark_label": config.BENCHMARK_LABEL,
        "link_provider": config.LINK_PROVIDER,
        "universe": {
            **uni_stats,
            "excluded_leverage_inverse": uni_stats.get("leverage_inverse", 0),
            "min_aum_eok": config.MIN_AUM_EOK,
            "min_turnover_eok": config.MIN_TURNOVER_EOK,
            "leverage_inverse_excluded": exclude_leverage,
        },
        "market": analyze_market(prices, config.BENCHMARK, config.BENCHMARK_LABEL),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="국내 ETF 가중모멘텀 × SEPA 스크리너")
    parser.add_argument("--top", type=int, default=config.TOP_N,
                        help=f"SEPA 분석 대상 상위 종목 수 (기본 {config.TOP_N})")
    parser.add_argument("--include-leverage", action="store_true",
                        help="레버리지·인버스 ETF를 유니버스에 포함 (기본은 제외)")
    parser.add_argument("--output", default=None,
                        help="HTML 출력 경로 (기본 docs/index.html)")
    args = parser.parse_args()

    data = run(args.top, exclude_leverage=not args.include_leverage)

    if not data["results"]:
        log.error("분석 결과가 비어 있습니다. 중단.")
        sys.exit(1)

    # JSON 저장
    data_dir = ROOT / config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    for path in (data_dir / "latest.json",
                 data_dir / f"scan_{data['scan_date']}.json"):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=_json_safe),
            encoding="utf-8")
    log.info("JSON 저장: %s", data_dir / "latest.json")

    # HTML 생성
    out_path = Path(args.output) if args.output else ROOT / config.DOCS_DIR / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(data), encoding="utf-8")
    log.info("HTML 저장: %s", out_path)

    # 사용법 페이지 — 스캔 결과와 무관하지만 임계값·배점을 config에서 끌어오므로
    # 설정을 바꾸면 설명도 같이 따라가도록 매번 다시 만든다.
    guide_path = out_path.parent / "guide.html"
    guide_path.write_text(build_guide_html({
        "buy_threshold": config.SEPA_BUY_THRESHOLD,
        "max_score": config.SEPA_MAX_SCORE,
        "template_min": config.TEMPLATE_PASS_MIN,
        "benchmark_label": config.BENCHMARK_LABEL,
        "min_aum_eok": config.MIN_AUM_EOK,
        "min_turnover_eok": config.MIN_TURNOVER_EOK,
        "link_label": LINK_LABELS.get(config.LINK_PROVIDER, "증권사"),
        "weight_str": " + ".join(
            f"{v}×{k}개월" for k, v in sorted(config.MOMENTUM_WEIGHTS.items())),
    }), encoding="utf-8")
    log.info("사용법 저장: %s", guide_path)

    buys = sum(1 for r in data["results"] if r["is_buy"])
    log.info("=== 완료 ===  유니버스 %d · 분석 %d개 · 매수 적격 %d개",
             data["universe_size"], len(data["results"]), buys)


if __name__ == "__main__":
    main()
