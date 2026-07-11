import os
import json
import re
import requests
import cloudscraper
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SENT_FILE = "sent_indicators.json"

# 지표명에 영문 원문을 병기할지 여부 (False면 한글만)
SHOW_ORIGINAL = True

# 서버 필터(importance[]=2,3)를 이미 통과하므로 사실상 안전망 역할.
# 별 파싱이 실패해 importance=0으로 잡히는 경우에도 살려주는 화이트리스트.
IMPORTANT_INDICATORS = [
    "CPI", "PCE", "PPI", "Non Farm", "Nonfarm", "NFP", "ADP",
    "Unemployment", "GDP", "Retail Sales", "ISM", "Federal Funds",
    "Interest Rate", "Initial Jobless", "Consumer Confidence",
    "Nonfarm Payrolls", "FOMC", "Powell", "Michigan",
]

# ─────────────────────────────────────────────────────────────
# CFTC 투기적 순포지션 자산명 (패턴 처리 — 딕셔너리에 개별 등록 불필요)
# ─────────────────────────────────────────────────────────────
CFTC_ASSET_KR = {
    "Crude Oil": "원유", "Gold": "금", "Silver": "은", "Copper": "구리",
    "Aluminium": "알루미늄", "Aluminum": "알루미늄", "Natural Gas": "천연가스",
    "Corn": "옥수수", "Wheat": "밀", "Soybeans": "대두", "Soybean Oil": "대두유",
    "Sugar": "설탕", "Cotton": "면화", "Coffee": "커피", "Cocoa": "코코아",
    "S&P 500": "S&P500", "Nasdaq 100": "나스닥100", "Nasdaq": "나스닥",
    "Russell 2000": "러셀2000", "VIX": "VIX",
    "EUR": "유로", "GBP": "파운드", "JPY": "엔", "CHF": "스위스프랑",
    "AUD": "호주달러", "NZD": "뉴질랜드달러", "CAD": "캐나다달러",
    "MXN": "멕시코페소", "BRL": "브라질헤알",
    "USD Index": "달러인덱스", "Bitcoin": "비트코인",
    "10-Year Note": "10년물 국채", "2-Year Note": "2년물 국채",
    "5-Year Note": "5년물 국채", "Treasury Bonds": "장기국채",
}

# 기간 접미사
PERIOD_KR = {
    "MoM": "전월비", "YoY": "전년비", "QoQ": "전분기비", "WoW": "전주비",
}

# ─────────────────────────────────────────────────────────────
# 지표명 한글 매핑 (긴 키 우선 매칭 → 구체적인 것부터 잡힘)
# ─────────────────────────────────────────────────────────────
INDICATOR_NAME_KR = {
    # ── 물가 ──────────────────────────────────────────────
    "Core CPI": "근원 소비자물가지수",
    "CPI Index": "소비자물가지수",
    "CPI": "소비자물가지수",
    "Core PPI": "근원 생산자물가지수",
    "PPI": "생산자물가지수",
    "Core PCE Price Index": "근원 개인소비지출 물가지수",
    "PCE Price Index": "개인소비지출 물가지수",
    "PCE": "개인소비지출",
    "GDP Price Index": "GDP 물가지수",
    "GDP Deflator": "GDP 디플레이터",
    "Core Import Price Index": "근원 수입물가지수",
    "Import Price Index": "수입물가지수",
    "Export Price Index": "수출물가지수",
    "Employment Cost Index": "고용비용지수(ECI)",
    "Michigan 1-Year Inflation Expectations": "미시간대 1년 기대인플레이션",
    "Michigan 5-Year Inflation Expectations": "미시간대 5년 기대인플레이션",
    "Michigan Inflation Expectations": "미시간대 기대인플레이션",

    # ── 고용 ──────────────────────────────────────────────
    "ADP Nonfarm Employment Change": "ADP 비농업고용",
    "ADP Non-Farm Employment Change": "ADP 비농업고용",
    "ADP Nonfarm": "ADP 비농업고용",
    "ADP Non-Farm": "ADP 비농업고용",
    "Private Nonfarm Payrolls": "민간 비농업고용",
    "Nonfarm Payrolls": "비농업고용지수",
    "Non Farm Payrolls": "비농업고용지수",
    "Government Payrolls": "정부부문 고용",
    "Manufacturing Payrolls": "제조업 고용",
    "Unemployment Rate": "실업률",
    "U6 Unemployment Rate": "U6 실업률",
    "Participation Rate": "경제활동참가율",
    "Average Hourly Earnings": "시간당 평균임금",
    "Average Weekly Hours": "주당 평균 근로시간",
    "Continuing Jobless Claims": "연속 실업수당청구건수",
    "Initial Jobless Claims": "신규 실업수당청구건수",
    "Jobless Claims 4-Week Avg": "실업수당청구 4주 평균",
    "JOLTS Job Openings": "구인이직보고서(JOLTS)",
    "Challenger Job Cuts": "챌린저 감원계획",
    "Nonfarm Productivity": "비농업 생산성",
    "Unit Labor Costs": "단위노동비용",

    # ── 성장 ──────────────────────────────────────────────
    "Atlanta Fed GDPNow": "애틀랜타 연준 GDPNow",
    "Real Consumer Spending": "실질 소비지출",
    "GDP Sales": "GDP 최종판매",
    "GDP": "국내총생산(GDP)",

    # ── 소비 ──────────────────────────────────────────────
    "Core Retail Sales": "근원 소매판매",
    "Retail Sales Control Group": "소매판매 통제그룹",
    "Retail Inventories Ex Auto": "자동차 제외 소매재고",
    "Retail Sales": "소매판매",
    "Personal Income": "개인소득",
    "Personal Spending": "개인소비지출",
    "Consumer Credit": "소비자신용",
    "Redbook": "레드북 소매판매",

    # ── 심리지수 ───────────────────────────────────────────
    "CB Consumer Confidence": "컨퍼런스보드 소비자신뢰지수",
    "Consumer Confidence": "소비자신뢰지수",
    "Michigan Consumer Sentiment": "미시간대 소비자심리지수",
    "Michigan Consumer Expectations": "미시간대 소비자기대지수",
    "Michigan Current Conditions": "미시간대 현재여건지수",
    "NFIB Small Business Optimism": "NFIB 소기업 낙관지수",
    "RCM/TIPP Economic Optimism": "RCM/TIPP 경제낙관지수",

    # ── 제조·서비스 PMI ────────────────────────────────────
    "ISM Manufacturing Employment": "ISM 제조업 고용지수",
    "ISM Manufacturing Prices": "ISM 제조업 가격지수",
    "ISM Manufacturing New Orders": "ISM 제조업 신규주문",
    "ISM Manufacturing PMI": "ISM 제조업 PMI",
    "ISM Non-Manufacturing Employment": "ISM 비제조업 고용지수",
    "ISM Non-Manufacturing Prices": "ISM 비제조업 가격지수",
    "ISM Non-Manufacturing PMI": "ISM 비제조업 PMI",
    "ISM Services Employment": "ISM 서비스업 고용지수",
    "ISM Services Prices": "ISM 서비스업 가격지수",
    "ISM Services New Orders": "ISM 서비스업 신규주문",
    "ISM Services PMI": "ISM 서비스업 PMI",
    "S&P Global Composite PMI": "S&P 글로벌 종합 PMI",
    "S&P Global Manufacturing PMI": "S&P 글로벌 제조업 PMI",
    "S&P Global Services PMI": "S&P 글로벌 서비스업 PMI",
    "Chicago PMI": "시카고 PMI",

    # ── 산업·주문·재고 ─────────────────────────────────────
    "Industrial Production": "산업생산",
    "Manufacturing Production": "제조업 생산",
    "Capacity Utilization Rate": "설비가동률",
    "Capacity Utilization": "설비가동률",
    "Core Durable Goods Orders": "근원 내구재주문",
    "Durable Goods Orders": "내구재주문",
    "Goods Orders Non Defense Ex Air": "핵심 자본재주문(국방·항공 제외)",
    "Factory Orders ex Transportation": "운송 제외 공장주문",
    "Factory Orders": "공장주문",
    "Business Inventories": "기업재고",
    "Wholesale Inventories": "도매재고",

    # ── 지역 연준 서베이 ───────────────────────────────────
    "Philadelphia Fed Manufacturing Index": "필라델피아 연준 제조업지수",
    "Philly Fed Manufacturing Index": "필라델피아 연준 제조업지수",
    "Philly Fed Employment": "필라델피아 연준 고용지수",
    "Philly Fed Prices Paid": "필라델피아 연준 지불가격지수",
    "NY Empire State Manufacturing Index": "뉴욕 엠파이어스테이트 제조업지수",
    "Empire State Manufacturing Index": "뉴욕 엠파이어스테이트 제조업지수",
    "Richmond Manufacturing Index": "리치먼드 연준 제조업지수",
    "Dallas Fed Manufacturing Business Index": "댈러스 연준 제조업지수",
    "Dallas Fed Services": "댈러스 연준 서비스업지수",
    "Kansas Fed Manufacturing Index": "캔자스시티 연준 제조업지수",
    "Chicago Fed National Activity": "시카고 연준 전미활동지수",
    "Leading Index": "경기선행지수",

    # ── 주택 ──────────────────────────────────────────────
    "Building Permits": "건축허가건수",
    "Housing Starts": "주택착공건수",
    "New Home Sales": "신규주택판매",
    "Existing Home Sales": "기존주택판매",
    "Pending Home Sales": "잠정주택판매",
    "NAHB Housing Market Index": "NAHB 주택시장지수",
    "S&P/CS HPI Composite": "S&P 케이스실러 주택가격지수",
    "House Price Index": "주택가격지수",
    "MBA Mortgage Applications": "MBA 주택담보대출 신청건수",
    "MBA 30-Year Mortgage Rate": "MBA 30년 모기지 금리",
    "Construction Spending": "건설지출",

    # ── 무역 ──────────────────────────────────────────────
    "Goods Trade Balance": "상품 무역수지",
    "Trade Balance": "무역수지",
    "Current Account": "경상수지",
    "Exports": "수출",
    "Imports": "수입",

    # ── 에너지 재고 ────────────────────────────────────────
    "Cushing Crude Oil Inventories": "쿠싱 원유재고",
    "Crude Oil Inventories": "원유재고",
    "Gasoline Inventories": "휘발유 재고",
    "Distillate Fuel Inventories": "정제유 재고",
    "Natural Gas Storage": "천연가스 재고",
    "API Weekly Crude Oil Stock": "API 주간 원유재고",
    "EIA Short-Term Energy Outlook": "EIA 단기 에너지전망",
    "IEA Monthly Report": "IEA 월간보고서",
    "OPEC Monthly Report": "OPEC 월간보고서",
    "WASDE Report": "USDA 수급전망보고서(WASDE)",

    # ── 연준 ──────────────────────────────────────────────
    "FOMC Economic Projections": "FOMC 경제전망(점도표)",
    "FOMC Press Conference": "FOMC 기자회견",
    "FOMC Meeting Minutes": "FOMC 의사록",
    "FOMC Statement": "FOMC 성명서",
    "Fed Interest Rate Decision": "연준 기준금리 결정",
    "Federal Funds Rate": "연방기금금리",
    "Interest Rate Decision": "기준금리 결정",
    "Fed Chair Powell Speaks": "파월 연준의장 발언",
    "Fed Chair Warsh Speaks": "워시 연준의장 발언",
    "FOMC Member": "FOMC 위원 발언",
    "Beige Book": "베이지북",
    "Fed's Balance Sheet": "연준 대차대조표",
    "Federal Budget Balance": "재정수지",

    # ── 국채 입찰 ──────────────────────────────────────────
    "30-Year Bond Auction": "30년물 국채 입찰",
    "20-Year Bond Auction": "20년물 국채 입찰",
    "10-Year Note Auction": "10년물 국채 입찰",
    "7-Year Note Auction": "7년물 국채 입찰",
    "5-Year Note Auction": "5년물 국채 입찰",
    "3-Year Note Auction": "3년물 국채 입찰",
    "2-Year Note Auction": "2년물 국채 입찰",
    "TIC Net Long-Term Transactions": "TIC 장기 순매수",

    # ── 기타 ──────────────────────────────────────────────
    "Thomson Reuters IPSOS PCSI": "톰슨로이터 입소스 소비자심리지수",
    "Tankan": "일본 단칸지수",

    # ── 중국 ──────────────────────────────────────────────
    "Caixin Manufacturing PMI": "차이신 제조업 PMI",
    "Caixin Services PMI": "차이신 서비스업 PMI",
    "Chinese Manufacturing PMI": "중국 제조업 PMI",
    "Chinese Non-Manufacturing PMI": "중국 비제조업 PMI",
    "Chinese Composite PMI": "중국 종합 PMI",
    "Fixed Asset Investment": "고정자산투자",
    "New Loans": "신규 위안화 대출",
    "M2 Money Stock": "M2 통화량",
    "Loan Prime Rate": "대출우대금리(LPR)",
    "Foreign Exchange Reserves": "외환보유고",
}

_SORTED_KR = sorted(INDICATOR_NAME_KR.items(), key=lambda x: -len(x[0]))


def translate_name(name: str) -> str:
    """지표명을 한글로 변환. 매핑 없으면 원문 그대로."""
    kor = None

    # 1) CFTC 투기적 순포지션 (자산 종류가 많아 패턴 처리)
    if "CFTC" in name and "speculative net positions" in name.lower():
        asset = re.sub(r"CFTC|speculative net positions", "", name, flags=re.I).strip()
        kor = f"CFTC {CFTC_ASSET_KR.get(asset, asset)} 투기적 순포지션"

    # 2) 베이커휴즈 시추기 수
    elif "Baker Hughes" in name and "Rig Count" in name:
        if "Oil" in name:
            kor = "베이커휴즈 원유 시추기 수"
        elif "Gas" in name:
            kor = "베이커휴즈 천연가스 시추기 수"
        elif "Total" in name:
            kor = "베이커휴즈 전체 시추기 수"
        else:
            kor = "베이커휴즈 시추기 수"

    # 3) 일반 딕셔너리 (긴 키 우선)
    else:
        for eng, k in _SORTED_KR:
            if eng.lower() in name.lower():
                kor = k
                break

    if not kor:
        return name  # 매핑 없으면 영문 원문

    # 기간 접미사 (MoM / YoY / QoQ) 붙여주기
    for eng_p, kor_p in PERIOD_KR.items():
        if re.search(rf"\b{re.escape(eng_p)}\b", name, flags=re.I):
            kor = f"{kor} ({kor_p})"
            break

    return f"{kor} ({name})" if SHOW_ORIGINAL else kor


# ─────────────────────────────────────────────────────────────
# 값 파싱 / 서프라이즈
# ─────────────────────────────────────────────────────────────
_UNIT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_value(s):
    """'75.7K' → 75700.0, '-2.3%' → -2.3, '1,234' → 1234.0"""
    if not s:
        return None
    s = s.strip().replace(",", "").replace("&nbsp;", "")
    m = re.search(r"-?\d+\.?\d*", s)
    if not m:
        return None
    v = float(m.group())
    for u, mult in _UNIT.items():
        # 숫자 바로 뒤에 붙은 단위만 인정 (%는 배수 없음)
        if re.search(rf"\d\s*{u}\b", s, flags=re.I):
            v *= mult
            break
    return v


def calculate_surprise(actual_str, forecast_str):
    a, f = parse_value(actual_str), parse_value(forecast_str)
    if a is None or f is None:
        return ""
    d = a - f
    if abs(d) < 1e-9:
        return "⚪ 예상 부합"
    mark = "🔺" if d > 0 else "🔻"
    word = "예상 상회" if d > 0 else "예상 하회"
    # 퍼센트 지표는 %p로 표기 (CPI 3.4% vs 3.3% → +0.1%p)
    if "%" in actual_str and "%" in forecast_str:
        return f"{mark} {word} ({d:+.1f}%p)"
    if f != 0:
        return f"{mark} {word} ({d / abs(f) * 100:+.1f}%)"
    return f"{mark} {word}"


# ─────────────────────────────────────────────────────────────
# 저장 / 로드
# ─────────────────────────────────────────────────────────────
def load_sent():
    try:
        with open(SENT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_sent(sent):
    with open(SENT_FILE, "w") as f:
        json.dump(sent, f, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────
# 캘린더 수집
# ─────────────────────────────────────────────────────────────
BROWSER_PROFILES = [
    {"browser": "chrome", "platform": "windows", "desktop": True},
    {"browser": "firefox", "platform": "windows", "desktop": True},
    {"browser": "chrome", "platform": "darwin", "desktop": True},
]


def fetch_calendar():
    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.investing.com/economic-calendar/",
    }
    now_utc = datetime.utcnow()
    payload = {
        "country[]": ["5", "35"],
        "importance[]": ["2", "3"],          # 2★ 이상만
        "timeZone": "55",                    # UTC
        "timeFilter": "timeRemain",
        "currentTab": "custom",
        "dateFrom": (now_utc - timedelta(days=1)).strftime("%Y-%m-%d"),
        "dateTo": (now_utc + timedelta(days=1)).strftime("%Y-%m-%d"),
        "submitFilters": "1",
        "limit_from": "0",
    }

    for i, prof in enumerate(BROWSER_PROFILES):
        try:
            scraper = cloudscraper.create_scraper(browser=prof)
            warm = scraper.get("https://www.investing.com/economic-calendar/", timeout=30)
            resp = scraper.post(url, headers=headers, data=payload, timeout=30)
            print(f"[시도 {i+1}/{len(BROWSER_PROFILES)}] 워밍업 {warm.status_code} / POST {resp.status_code}")
            if resp.status_code == 200:
                return parse_calendar(resp.json().get("data", ""))
        except Exception as e:
            print(f"[시도 {i+1}] 실패: {e}")

    print("❌ 캘린더 수집 실패 (모든 프로필 소진)")
    return []


def parse_calendar(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr", class_="js-event-item")
    indicators = []
    star_ok = False

    for row in rows:
        try:
            event_cell = row.find("td", class_="event")
            if not event_cell:
                continue
            name = event_cell.get_text(strip=True)

            importance = len(row.find_all("i", class_="grayFullBullishIcon"))
            if importance > 0:
                star_ok = True

            def cell(prefix):
                c = row.find("td", id=lambda x: x and x.startswith(prefix))
                t = c.get_text(strip=True) if c else ""
                return "" if t in ("&nbsp;", "\xa0") else t

            actual = cell("eventActual_")
            forecast = cell("eventForecast_")
            prev = cell("eventPrevious_")

            # 실제값 없으면 아직 미발표 (또는 리포트성 이벤트) → 스킵
            if not actual:
                continue

            is_important = any(kw.lower() in name.lower() for kw in IMPORTANT_INDICATORS)
            if importance < 2 and not is_important:
                continue

            # 발표시각: data-event-datetime은 UTC → KST 변환
            dt_attr = row.get("data-event-datetime", "")
            try:
                dt_kst = datetime.strptime(dt_attr, "%Y/%m/%d %H:%M:%S") + timedelta(hours=9)
                kst_key = dt_kst.strftime("%Y-%m-%d %H:%M")
                kst_disp = dt_kst.strftime("%m.%d %H:%M")
            except Exception:
                tc = row.find("td", class_="time")
                kst_key = kst_disp = tc.get_text(strip=True) if tc else "?"

            indicators.append({
                "id": row.get("id", ""),
                "name": name,
                "kst_key": kst_key,
                "kst_disp": kst_disp,
                "actual": actual,
                "forecast": forecast,
                "prev": prev,
                "importance": importance,
            })
        except Exception:
            continue

    if rows and not star_ok:
        print("⚠️ 경고: 중요도(별) 파싱이 전부 0 — investing.com HTML 구조 변경 가능성")

    return indicators


# ─────────────────────────────────────────────────────────────
# 메시지
# ─────────────────────────────────────────────────────────────
FOOTER = '\n\n<i>📌 Bilanx Research</i>\n<a href="https://t.me/davidstocknew">📎 주식소리통 NEO</a>'
MAX_LEN = 3800  # 텔레그램 4096자 여유분


def build_blocks(indicators):
    blocks = []
    for ind in indicators:
        stars = "⭐" * ind["importance"]
        lines = [f"{stars} <b>{translate_name(ind['name'])}</b>"]
        detail = f"실제 <code>{ind['actual']}</code>"
        if ind["forecast"]:
            sp = calculate_surprise(ind["actual"], ind["forecast"])
            detail += f"  예상 <code>{ind['forecast']}</code>"
            if sp:
                detail += f"  {sp}"
        if ind["prev"]:
            detail += f"  <i>(이전 {ind['prev']})</i>"
        lines.append(detail)
        blocks.append("\n".join(lines))
    return blocks


def build_messages(kst_disp, indicators):
    """같은 발표시각 지표를 한 메시지로 묶되, 길면 자동 분할."""
    header = f"📊 <b>경제지표 속보</b>  <i>{kst_disp}</i>"
    blocks = build_blocks(indicators)

    messages, cur = [], [header]
    for b in blocks:
        candidate = "\n\n".join(cur + [b]) + FOOTER
        if len(candidate) > MAX_LEN and len(cur) > 1:
            messages.append("\n\n".join(cur) + FOOTER)
            cur = [header, b]
        else:
            cur.append(b)
    if len(cur) > 1:
        messages.append("\n\n".join(cur) + FOOTER)
    return messages


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        ok = resp.json().get("ok", False)
        if not ok:
            print(f"텔레그램 응답: {resp.text[:200]}")
        return ok
    except Exception as e:
        print(f"텔레그램 오류: {e}")
        return False


# ─────────────────────────────────────────────────────────────
def main():
    print(f"🚀 봇 실행 - {datetime.utcnow()} UTC")
    sent = load_sent()
    indicators = fetch_calendar()
    if not indicators:
        print("발표 완료된 지표 없음")
        return

    new = [i for i in indicators if i["id"] not in sent]
    if not new:
        print(f"신규 없음 (수집 {len(indicators)}건, 전부 전송 완료분)")
        return

    # 같은 발표시각끼리 묶기
    groups = {}
    for ind in new:
        groups.setdefault(ind["kst_key"], []).append(ind)

    print(f"새 지표 {len(new)}개 / {len(groups)}개 시각대")

    for key in sorted(groups):
        batch = groups[key]
        batch.sort(key=lambda x: (-x["importance"], x["name"]))  # 중요도 높은 순
        disp = batch[0]["kst_disp"]

        all_ok = True
        for msg in build_messages(disp, batch):
            if not send_telegram(msg):
                all_ok = False

        if all_ok:
            for ind in batch:
                sent[ind["id"]] = datetime.utcnow().isoformat()
            print(f"✅ {disp} — {len(batch)}개 전송: " + ", ".join(i["name"] for i in batch))
        else:
            print(f"❌ {disp} — 전송 실패 (다음 사이클 재시도)")

    save_sent(sent)


if __name__ == "__main__":
    main()
