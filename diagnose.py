import cloudscraper
from bs4 import BeautifulSoup

url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
headers = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.investing.com/economic-calendar/",
}
payload = {
    "country[]": ["5", "35"],
    "importance[]": ["1", "2", "3"],   # 1★까지 전부
    "timeZone": "55",                  # UTC
    "timeFilter": "timeRemain",
    "currentTab": "custom",
    "dateFrom": "2026-07-10",
    "dateTo": "2026-07-10",
    "submitFilters": "1",
    "limit_from": "0",
}

PROFILES = [
    {"browser": "chrome",  "platform": "windows", "desktop": True},
    {"browser": "firefox", "platform": "windows", "desktop": True},
    {"browser": "chrome",  "platform": "darwin",  "desktop": True},
]

html = ""
for i, prof in enumerate(PROFILES):
    try:
        s = cloudscraper.create_scraper(browser=prof)
        w = s.get("https://www.investing.com/economic-calendar/", timeout=30)
        r = s.post(url, headers=headers, data=payload, timeout=30)
        print(f"[시도 {i+1}] 워밍업 {w.status_code} / POST {r.status_code}")
        if r.status_code == 200:
            html = r.json().get("data", "")
            break
    except Exception as e:
        print(f"[시도 {i+1}] 실패: {e}")

if not html:
    print("❌ 전부 실패")
    raise SystemExit

soup = BeautifulSoup(html, "html.parser")
rows = soup.find_all("tr", class_="js-event-item")
print(f"\n총 {len(rows)}개 행\n")
print(f"{'UTC':<7}{'KST':<7}{'★':<5}{'ID':<20}{'실제':<12}{'예상':<12}{'이전':<12} 지표명")
print("-" * 130)

for row in rows:
    rid = row.get("id", "")
    t = row.find("td", class_="time")
    t = t.get_text(strip=True) if t else ""
    ev = row.find("td", class_="event")
    name = ev.get_text(strip=True) if ev else ""
    imp = len(row.find_all("i", class_="grayFullBullishIcon"))

    def cell(p):
        c = row.find("td", id=lambda x: x and x.startswith(p))
        return c.get_text(strip=True) if c else ""

    a, f, p = cell("eventActual_"), cell("eventForecast_"), cell("eventPrevious_")

    kst = ""
    if ":" in t:
        try:
            hh, mm = t.split(":")
            kst = f"{(int(hh)+9)%24:02d}:{mm}"
        except Exception:
            pass

    star = "★" * imp
    print(f"{t:<7}{kst:<7}{star:<5}{rid:<20}{a:<12}{f:<12}{p:<12} {name}")
