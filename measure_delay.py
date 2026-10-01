# -*- coding: utf-8 -*-
"""실행 간격과 '발표 → 발송' 지연을 따로 잰다 (2026-10-01).

  python measure_delay.py            최근 예약 실행 간격(GitHub API, 공개 저장소라 토큰 불필요) + sent_indicators.json 의 발표→발송 지연
  python measure_delay.py --days 3   최근 3일만

두 숫자는 다른 것이다 — 실행 간격은 "봇이 얼마나 자주 깨어났나", 발송 지연은 "지표가 나온 뒤 채널에 가기까지 몇 분"이다.
발송 지연은 10-01 이후 기록(rel 발표시각이 있는 항목)에서만 잴 수 있다. 옛 기록은 보낸 시각뿐이라 제외한다.
"""
import json, sys, statistics as st, urllib.request
from datetime import datetime, timezone, timedelta

REPO = "bilanxlyc/bilanx-econ-bot"
days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
since = datetime.now(timezone.utc) - timedelta(days=days)

runs = []
for page in (1, 2, 3):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs?event=schedule&per_page=100&page={page}",
                                 headers={"User-Agent": "bilanx-measure", "Accept": "application/vnd.github+json"})
    d = json.load(urllib.request.urlopen(req, timeout=30)).get("workflow_runs", [])
    runs += d
    if len(d) < 100:
        break
ts = sorted(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) for r in runs)
ts = [t for t in ts if t >= since]
if len(ts) >= 2:
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:])]
    print(f"[실행 간격] 최근 {days}일 예약 실행 {len(ts)}회 · 간격 중앙값 {st.median(gaps):.0f}분 · p90 {sorted(gaps)[int(len(gaps)*.9)]:.0f}분 · 최대 {max(gaps):.0f}분")
    slot_min = [t.minute for t in ts]
    print(f"           깨어난 분(minute) 분포: 중앙값 {st.median(slot_min):.0f}분 (크론 3분 기준 → 지연 중앙값 {st.median(slot_min)-3:.0f}분)")
else:
    print("[실행 간격] 표본 부족")

sent = json.load(open("sent_indicators.json", encoding="utf-8"))
KST = timezone(timedelta(hours=9))
delays = []
for k, v in sent.items():
    if not isinstance(v, dict) or not v.get("rel"):
        continue
    try:
        rel = datetime.strptime(v["rel"], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        snt = datetime.fromisoformat(v["sent"]).replace(tzinfo=timezone.utc)
    except Exception:
        continue
    if snt >= since:
        delays.append(((snt - rel).total_seconds() / 60, v.get("name", k), v["rel"]))
if delays:
    ds = sorted(x[0] for x in delays)
    print(f"[발표→발송] 최근 {days}일 {len(delays)}건 · 중앙값 {st.median(ds):.0f}분 · p90 {ds[int(len(ds)*.9)]:.0f}분 · 최대 {ds[-1]:.0f}분")
    for d, n, r in sorted(delays, key=lambda x: -x[0])[:5]:
        print(f"           가장 늦은 것: {n} 발표 {r} KST → {d:.0f}분 뒤 발송")
else:
    print("[발표→발송] 10-01 이후 기록이 아직 없다 (발표 시각이 함께 적힌 항목만 잴 수 있다)")
