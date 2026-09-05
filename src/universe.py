"""국내 상장 ETF 유니버스 수집 + 주가 다운로드

원본(S&P 500)의 `universe.py`를 국내 ETF로 옮긴 모듈이다. 두 가지가 다르다.

1. 종목 목록 — Wikipedia 대신 네이버 금융 ETF 목록 API를 쓴다. 한 번의
   요청으로 전 종목의 코드·이름·분류·순자산·거래대금·NAV를 함께 준다.
   KRX 공식 API(pykrx)는 2025년 이후 로그인을 요구해 무인 실행에 쓸 수 없다.
2. 레버리지·인버스 제외 — KRX 상품명 규칙상 해당 상품은 이름에 반드시
   '레버리지' / '인버스' / 배수 표기가 포함되므로 이름 기반으로 걸러낸다.

주가는 원본과 동일하게 yfinance 배치 다운로드를 쓴다 (국내 ETF는 `.KS` 접미).
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

log = logging.getLogger(__name__)

NAVER_ETF_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://finance.naver.com/sise/etf.naver",
}

# 네이버 ETF 탭 코드 → 한글 분류 (원본의 GICS 섹터 뱃지 자리)
TAB_KR = {
    1: "국내지수",
    2: "업종·테마",
    3: "파생",
    4: "해외주식",
    5: "원자재",
    6: "채권",
    7: "기타",
}

# 레버리지·인버스 판별 패턴
#   '레버리지', '인버스' — KRX 상품명 표기 규칙상 반드시 포함된다
#   숫자+X (2X, 3X, ２Ｘ) — 배수형 상품. 'KODEX', 'INDXX' 같은 단어의 X가
#   걸리지 않도록 앞자리가 숫자이고 그 앞이 영숫자가 아닐 때만 매치한다.
LEVERAGE_INVERSE_RE = re.compile(
    r"레버리지|인버스|곱버스"
    r"|(?<![A-Za-z0-9])[2-9](?:\.\d)?\s?[XxＸ](?![A-Za-z])"
    r"|[-−]\s?1\s?[XxＸ]"
    r"|[２３４５]Ｘ"
)


def is_leverage_or_inverse(name: str) -> bool:
    """ETF 이름이 레버리지 또는 인버스 상품인지 판정한다."""
    return bool(LEVERAGE_INVERSE_RE.search(name or ""))


def _fetch_naver_etf_list() -> list:
    """네이버 금융에서 전체 상장 ETF 목록을 가져온다 (단일 요청)."""
    r = requests.get(NAVER_ETF_URL, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    payload = r.json()
    items = (payload.get("result") or {}).get("etfItemList") or []
    if not items:
        raise ValueError("ETF 목록이 비어 있습니다")
    return items


def get_etf_list(cache_path: str = None,
                 exclude_leverage_inverse: bool = True,
                 min_aum_eok: float = 0,
                 min_price: float = 0) -> tuple:
    """국내 상장 ETF 목록을 수집·정제한다.

    네이버 요청이 실패하면 저장해 둔 캐시로 폴백한다. 성공하면 캐시를 갱신한다.

    Returns:
        (DataFrame[code, name, category, price, nav, premium_pct,
                   aum_eok, turnover_eok, volume],
         stats dict — 단계별 제외 종목 수)
    """
    cache = Path(cache_path) if cache_path else None
    source, fetched_at = "naver", None

    try:
        items = _fetch_naver_etf_list()
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"fetched_at": datetime.now().isoformat(timespec="seconds"),
                            "items": items}, ensure_ascii=False),
                encoding="utf-8")
        log.info("ETF 목록 수신: %d종목 (네이버)", len(items))
    except Exception as e:
        if not (cache and cache.exists()):
            raise RuntimeError(f"ETF 목록 수집 실패, 캐시도 없음: {e}") from e
        cached = json.loads(cache.read_text(encoding="utf-8"))
        items = cached["items"]
        source, fetched_at = "cache", cached.get("fetched_at")
        log.warning("네이버 조회 실패(%s) — 캐시(%s) 사용: %d종목",
                    e, fetched_at, len(items))

    df = pd.DataFrame(items)
    df = df.rename(columns={
        "itemcode": "code",
        "itemname": "name",
        "nowVal": "price",
        "marketSum": "aum_eok",     # 순자산총액 (억원)
        "amonut": "turnover_mkrw",  # 당일 거래대금 (백만원) — 원문 오타 그대로
        "quant": "volume",
    })
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["category"] = df["etfTabCode"].map(TAB_KR).fillna("기타")
    df["turnover_eok"] = df["turnover_mkrw"] / 100.0   # 백만원 → 억원

    # NAV 대비 괴리율 (%). 양수 = 고평가 거래
    df["premium_pct"] = ((df["price"] - df["nav"]) / df["nav"] * 100).where(df["nav"] > 0)

    stats = {"listed_total": len(df), "source": source,
             "source_fetched_at": fetched_at}

    # 레버리지·인버스는 실제로 걸러내든 아니든 항상 세어 둔다 (리포트 표시용)
    lev_mask = df["name"].apply(is_leverage_or_inverse)
    stats["leverage_inverse"] = int(lev_mask.sum())

    if exclude_leverage_inverse:
        log.info("레버리지·인버스 제외: %d종목", stats["leverage_inverse"])
        df = df[~lev_mask]

    if min_aum_eok > 0:
        before = len(df)
        df = df[df["aum_eok"] >= min_aum_eok]
        stats["below_min_aum"] = before - len(df)
        log.info("순자산 %g억 미만 제외: %d종목", min_aum_eok, stats["below_min_aum"])

    if min_price > 0:
        before = len(df)
        df = df[df["price"] >= min_price]
        stats["below_min_price"] = before - len(df)
        log.info("주가 %g원 미만 제외: %d종목", min_price, stats["below_min_price"])

    df = df.reset_index(drop=True)
    stats["candidates"] = len(df)
    log.info("유니버스 확정: 전체 %d → 후보 %d종목", stats["listed_total"], len(df))

    cols = ["code", "name", "category", "price", "nav", "premium_pct",
            "aum_eok", "turnover_eok", "volume"]
    return df[cols], stats


def download_prices(codes: list, years: int = 2,
                    benchmark: str = "^KS11") -> dict:
    """ETF 일봉 OHLCV를 배치 다운로드한다.

    국내 ETF는 KOSPI 시장에 상장되므로 yfinance 심볼은 `<6자리코드>.KS`.
    반환 dict의 키는 접미사를 뗀 6자리 코드이며, 벤치마크만 원래 심볼을 쓴다.

    Returns:
        {code: DataFrame(Open, High, Low, Close, Volume)}
    """
    end = datetime.now() + timedelta(days=1)          # yfinance end는 exclusive
    start = end - timedelta(days=years * 365 + 45)

    codes = list(dict.fromkeys(codes))
    symbols = [f"{c}.KS" for c in codes] + [benchmark]
    log.info("주가 다운로드: %d종목 × %d년", len(symbols), years)

    raw = yf.download(
        symbols,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    prices, failed = {}, []
    for symbol in symbols:
        key = benchmark if symbol == benchmark else symbol[:-3]
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                df = raw.xs(symbol, level="Ticker", axis=1).copy()
            else:
                df = raw.copy()
            df = df.dropna(subset=["Close"])
            if len(df) < 200:          # Phase 분류에 200일 필요
                failed.append(key)
                continue
            prices[key] = df
        except Exception:
            failed.append(key)

    log.info("다운로드 완료: 성공 %d, 제외 %d (상장 1년 미만 등)",
             len(prices), len(failed))

    return prices


def filter_by_turnover(prices: dict, min_turnover_eok: float,
                       window: int = 20, exclude: list = None) -> dict:
    """20일 평균 거래대금이 기준 미달인 종목을 제거한다.

    네이버가 주는 거래대금은 당일 한 건뿐이라 휴장 직후나 이벤트 당일에
    왜곡된다. 종가×거래량의 20일 평균으로 다시 판정한다.
    """
    if min_turnover_eok <= 0:
        return prices

    keep, dropped = {}, 0
    exclude = set(exclude or [])

    for code, df in prices.items():
        if code in exclude:
            keep[code] = df
            continue
        turnover = (df["Close"] * df["Volume"]).iloc[-window:].mean() / 1e8  # 억원
        if pd.isna(turnover) or turnover < min_turnover_eok:
            dropped += 1
            continue
        keep[code] = df

    log.info("%d일 평균 거래대금 %g억 미만 제외: %d종목",
             window, min_turnover_eok, dropped)
    return keep


def get_price_matrix(prices: dict) -> pd.DataFrame:
    """각 종목 Close를 하나의 DataFrame(Date × Code)으로 합친다."""
    matrix = pd.DataFrame({c: df["Close"] for c, df in prices.items()})
    return matrix.sort_index()


def avg_turnover_eok(price_data: pd.DataFrame, window: int = 20) -> float:
    """최근 window일 평균 거래대금 (억원)."""
    val = (price_data["Close"] * price_data["Volume"]).iloc[-window:].mean() / 1e8
    return float(val) if pd.notna(val) else 0.0
