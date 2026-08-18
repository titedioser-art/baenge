#!/usr/bin/env python3
"""
Naver 블로그 누적 방문자 수를 읽어와 index.html 4개 파일을 갱신한다.

- 네이버가 공식 API를 제공하지 않으므로 페이지 구조에서 숫자를 추출한다.
- 추출 실패 / 값이 이상하면 아무것도 고치지 않고 종료 코드 1로 실패시킨다.
  (잘못된 숫자가 사이트에 올라가는 것보다 멈추는 편이 안전하다)
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BLOG_ID = "bbh4313"
STATE_FILE = "data/visitors.json"
TARGETS = ["index.html", "ko/index.html", "en/index.html", "zh/index.html"]

# 하루 증가 상한 — 이보다 크게 뛰면 잘못 읽은 것으로 간주
MAX_DAILY_JUMP = 60000

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CANDIDATES = [
    "https://blog.naver.com/NVisitorgp4Ajax.naver?blogId=" + BLOG_ID,
    "https://blog.naver.com/widget/TotalVisitorWidget.naver?blogId=" + BLOG_ID,
    "https://m.blog.naver.com/" + BLOG_ID,
    "https://blog.naver.com/" + BLOG_ID,
]


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://blog.naver.com/" + BLOG_ID,
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def extract_total(text, floor):
    """floor 이상인 7자리 숫자 후보 중 가장 작은 값을 고른다."""
    found = set()

    # 콤마 있는 형태: 2,845,363
    for m in re.finditer(r"\b\d{1,3}(?:,\d{3}){2,}\b", text):
        found.add(int(m.group(0).replace(",", "")))

    # 콤마 없는 7~8자리
    for m in re.finditer(r"\b\d{7,8}\b", text):
        n = int(m.group(0))
        # 날짜(20260818) 같은 값 제외
        if 20000000 <= n <= 21001231:
            continue
        found.add(n)

    ok = sorted(n for n in found if floor <= n <= floor + MAX_DAILY_JUMP)
    return ok[0] if ok else None


def month_labels(now):
    return {
        "ko": "%d년 %d월 기준" % (now.year, now.month),
        "en": "(as of %s %d)" % (now.strftime("%B"), now.year),
        "zh": "截至%d年%d月" % (now.year, now.month),
    }


def main():
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    state = json.load(open(STATE_FILE, encoding="utf-8"))
    old_total = int(state["total"])
    print("현재 저장된 누적 방문자: {:,}".format(old_total))

    new_total = None
    for url in CANDIDATES:
        try:
            body = fetch(url)
        except Exception as e:
            print("  실패 %s -> %s" % (url, e))
            continue
        got = extract_total(body, old_total)
        print("  %s -> %s" % (url, "{:,}".format(got) if got else "찾지 못함"))
        if got:
            new_total = got
            break

    if new_total is None:
        print("\n[중단] 누적 방문자 수를 읽지 못했습니다. 파일을 수정하지 않습니다.")
        print("네이버 페이지 구조가 바뀌었을 수 있습니다. 수동 갱신이 필요합니다.")
        return 1

    if new_total == old_total:
        print("\n변동 없음. 종료합니다.")
        return 0

    print("\n새 누적 방문자: {:,} (+{:,})".format(new_total, new_total - old_total))
    if dry_run:
        print("DRY_RUN 모드 — 파일을 수정하지 않았습니다.")
        return 0

    now = datetime.now(timezone(timedelta(hours=9)))
    labels = month_labels(now)

    old_str = "{:,}".format(old_total)
    new_str = "{:,}".format(new_total)
    old_short = "%.1f" % (old_total / 1_000_000)
    new_short = "%.1f" % (new_total / 1_000_000)

    for path in TARGETS:
        if not os.path.exists(path):
            print("건너뜀 (없음): " + path)
            continue
        html = open(path, encoding="utf-8").read()
        before = html

        html = html.replace(old_str, new_str)
        if old_short != new_short:
            html = html.replace(
                '<div class="hero-stat-num">%s<span class="cy">M+</span></div>' % old_short,
                '<div class="hero-stat-num">%s<span class="cy">M+</span></div>' % new_short)

        html = re.sub(r"\d{4}년 \d{1,2}월 기준", labels["ko"], html)
        html = re.sub(r"\(as of [A-Z][a-z]+ \d{4}\)", labels["en"], html)
        html = re.sub(r"截至\d{4}年\d{1,2}月", labels["zh"], html)

        if html != before:
            open(path, "w", encoding="utf-8").write(html)
            print("갱신: " + path)

    state.update({
        "total": new_total,
        "updated": now.strftime("%Y-%m-%d"),
    })
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
