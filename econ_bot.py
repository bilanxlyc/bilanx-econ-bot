import os
import json
import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SENT_FILE = "sent_indicators.json"

IMPORTANT_INDICATORS = [
    "CPI", "Core CPI", "PCE", "Non Farm", "Nonfarm", "NFP",
    "Unemployment", "GDP", "Retail Sales", "ISM Manufacturing",
    "ISM Services", "Federal Funds", "Interest Rate",
    "PPI", "Initial Jobless", "Consumer Confidence",
    "한국 수출", "한국 금리", "한국 CPI"
]

INDICATOR_NAME_KR = {
    "Core CPI": "근원 소비자물가지수",
    "CPI": "소비자물가지수",
    "PCE": "개인소비지출",
    "ADP Nonfarm Employment Change": "ADP 비농업고용",
    "ADP Non-Farm": "ADP 비농업고용",
    "Non Farm Payrolls": "비농업고용지수",
    "Nonfarm Payrolls": "비농업고용지수",
    "NFP": "비농업고용지수",
    "Unemployment Rate": "실업률",
    "Atlanta Fed GDPNow": "애틀랜타 연준 GDPNow",
    "GDP": "국내총생산",
    "Retail Sales": "소매판매",
    "ISM Manufacturing PMI": "ISM 제조업 PMI",
    "ISM Manufacturing Employment": "ISM 제조업 고용지수",
    "ISM Manufacturing Prices": "ISM 제조업 가격지수",
    "ISM Services PMI": "ISM 서비스업 PMI",
    "ISM Services": "ISM 서비스업지수",
    "S&P Global Manufacturing PMI": "S&P 글로벌 제조업 PMI",
    "Federal Funds Rate": "연방기금금리",
    "Interest Rate Decision": "기준금리 결정",
    "Interest Rate": "금리",
    "PPI": "생산자물가지수",
    "Initial Jobless Claims": "신규실업수당청구건수",
    "Initial Jobless": "신규실업수당청구건수",
    "CB Consumer Confidence": "소비자신뢰지수",
    "Consumer Confidence": "소비자신뢰지수",
    "JOLTS Job Openings": "구인이직보고서(JOLTS)",
    "Chicago PMI": "시카고 PMI",
    "Cushing Crude Oil Inventories": "쿠싱 원유재고",
    "Crude Oil Inventories": "원유재고",
    "API Weekly Crude Oil Stock": "API 주간 원유재고",
    "Construction Spending": "건설지출",
    "Tankan": "일본 단칸지수",
    "S&P/CS HPI Composite": "S&P/CS 주택가격지수",
    "한국 수출": "한국 수출",
    "한국 금리": "한국 기준금리",
    "한국 CPI": "한국 소비자물가지수",
}

def translate_name(name):
    for eng, kor in sorted(INDICATOR_NAME_KR.items(), key=lambda x: -len(x[0])):
        if eng.lower() in name.lower():
            return f"{kor} ({name})"
    return name

def load_sent():
    try:
        with open(SENT_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_sent(sent):
    with open(SENT_FILE, "w") as f:
        json.dump(sent, f)

def fetch_calendar():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.investing.com/economic-calendar/",
    }
    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

    now_utc = datetime.utcnow()
    date_from = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")

    payload = {
        "country[]": ["5", "35"],
        "importance[]": ["2", "3"],
        "timeZone": "55",
        "timeFilter": "timeRemain",
        "currentTab": "custom",
        "dateFrom": date_from,
        "dateTo": date_to,
        "submitFilters": "1",
        "limit_from": "0",
    }
    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        print(f"응답 코드: {resp.status_code}")
        print(f"응답 앞부분: {resp.text[:300]}")
        data = resp.json()
        html = data.get("data", "")
        return parse_calendar(html)
    except Exception as e:
        print(f"캘린더 수집 오류: {e}")
        return []

def parse_calendar(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr", class_="js-event-item")
    indicators = []
    for row in rows:
        try:
            time_cell = row.find("td", class_="time")
            if not time_cell:
                continue
            time_str = time_cell.get_text(strip=True)
            event_cell = row.find("td", class_="event")
            if not event_cell:
                continue
            name = event_cell.get_text(strip=True)
            importance = len(row.find_all("i", class_="grayFullBullishIcon"))

            actual_cell = row.find("td", id=lambda x: x and x.startswith("eventActual_"))
            actual = actual_cell.get_text(strip=True) if actual_cell else ""
            forecast_cell = row.find("td", id=lambda x: x and x.startswith("eventForecast_"))
            forecast = forecast_cell.get_text(strip=True) if forecast_cell else ""
            prev_cell = row.find("td", id=lambda x: x and x.startswith("eventPrevious_"))
            prev = prev_cell.get_text(strip=True) if prev_cell else ""

            if not actual or actual == "&nbsp;":
                continue
            is_important = any(kw.lower() in name.lower() for kw in IMPORTANT_INDICATORS)
            if importance < 2 and not is_important:
                continue
            indicators.append({
                "id": row.get("id", ""),
                "name": name,
                "time": time_str,
                "actual": actual,
                "forecast": forecast,
                "prev": prev,
                "importance": importance,
            })
        except:
            continue
    return indicators

def calculate_surprise(actual_str, forecast_str):
    try:
        actual = float(re.sub(r"[^\d.\-]", "", actual_str))
        forecast = float(re.sub(r"[^\d.\-]", "", forecast_str))
        surprise = actual - forecast
        if surprise > 0:
            return f"🔴 예상 상회 +{surprise:.2f}"
        elif surprise < 0:
            return f"🔵 예상 하회 {surprise:.2f}"
        else:
            return "⚪ 예상 부합"
    except:
        return ""

def format_message(indicators):
    now_kst = (datetime.utcnow() + timedelta(hours=9)).strftime("%m.%d %H:%M")
    lines = [f"📊 <b>경제지표 속보</b>  <i>{now_kst}</i>"]
    for ind in indicators:
        stars = "⭐" * ind["importance"]
        surprise = calculate_surprise(ind["actual"], ind["forecast"])
        display_name = translate_name(ind["name"])
        lines.append(f"\n{stars} <b>{display_name}</b>")
        detail = f"실제 <code>{ind['actual']}</code>"
        if ind["forecast"]:
            detail += f"  예상 <code>{ind['forecast']}</code>  {surprise}"
        if ind["prev"]:
            detail += f"  <i>(이전 {ind['prev']})</i>"
        lines.append(detail)
    lines.append("\n<i>📌 Bilanx Research</i>")
    return "\n".join(lines)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json().get("ok", False)
    except Exception as e:
        print(f"텔레그램 오류: {e}")
        return False

def main():
    print(f"🚀 봇 실행 - {datetime.utcnow()}")
    sent = load_sent()
    indicators = fetch_calendar()
    if not indicators:
        print("새 발표 지표 없음")
        return
    new_indicators = [ind for ind in indicators if ind["id"] not in sent]
    if not new_indicators:
        print("이미 전송한 지표만 있음")
        return
    print(f"새 지표 {len(new_indicators)}개 발견!")
    for ind in new_indicators:
        message = format_message([ind])
        success = send_telegram(message)
        if success:
            sent[ind["id"]] = datetime.utcnow().isoformat()
            print(f"✅ 전송 완료: {ind['name']}")
        else:
            print(f"❌ 전송 실패: {ind['name']}")
    save_sent(sent)

if __name__ == "__main__":
    main()
