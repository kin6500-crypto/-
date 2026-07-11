"""
매일 아침 WSJ / Bloomberg RSS에서 미국 경제 뉴스를 가져와
index.html 과 아침신보-artifact.html 의 '미국경제' 카테고리에 추가하는 스크립트.
GitHub Actions가 매일 자동으로 이 스크립트를 실행합니다.
"""

import re
import sys
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REPO_FILES = ["index.html", "아침신보-artifact.html"]
FEEDS = [
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "WSJ"),
    ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg"),
]
TIMES = ["05:30", "05:50", "06:10", "06:30", "06:50", "07:10", "07:30"]
MAX_NEW_PER_DAY = 4
KEEP_DAYS = 7


def fetch_items(url, source, limit=6):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; achim-sinbo-bot/1.0)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title_el = item.find("title")
        desc_el = item.find("description")
        title = (title_el.text or "").strip() if title_el is not None else ""
        desc = (desc_el.text or "").strip() if desc_el is not None else ""
        desc = re.sub(r"<[^>]+>", "", desc)  # strip any HTML tags in description
        desc = html.unescape(desc)
        title = html.unescape(title)
        if title:
            items.append((title.strip(), desc.strip()[:220], source))
        if len(items) >= limit:
            break
    return items


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def prune_old_dates(content, today_date):
    def repl(m):
        d = m.group(1)
        try:
            d_date = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return m.group(0)
        if (today_date - d_date).days > KEEP_DAYS:
            return ""
        return m.group(0)

    return re.sub(r"'(\d{4}-\d{2}-\d{2})':\s*\[.*?\],\n", repl, content, flags=re.DOTALL)


def existing_titles_for_today(content, today_iso):
    pattern = re.compile(r"'" + re.escape(today_iso) + r"':\s*\[(.*?)\],\n", re.DOTALL)
    m = pattern.search(content)
    if not m:
        return None, []
    block = m.group(1)
    titles = re.findall(r"title:\s*'((?:[^'\\]|\\.)*)'", block)
    titles += re.findall(r'title:\s*"((?:[^"\\]|\\.)*)"', block)
    return m, titles


def build_entry_line(time_str, source, title, desc, has_image):
    img = ", hasImage: true" if has_image else ""
    return (
        '      { category: \'미국경제\', time: "%s · %s", title: "%s", summary: "%s"%s },\n'
        % (time_str, source, esc(title), esc(desc), img)
    )


def update_file(path, today_iso, today_date, new_items):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = prune_old_dates(content, today_date)

    m, existing_titles = existing_titles_for_today(content, today_iso)
    existing_lower = {t.lower()[:24] for t in existing_titles}

    entries = []
    ti = 0
    for title, desc, source in new_items:
        if len(entries) >= MAX_NEW_PER_DAY:
            break
        key = title.lower()[:24]
        if key in existing_lower:
            continue
        entries.append(build_entry_line(TIMES[ti % len(TIMES)], source, title, desc, len(entries) % 2 == 0))
        existing_lower.add(key)
        ti += 1

    if not entries:
        print(f"[{path}] 추가할 새 기사가 없습니다 (중복이거나 피드 실패).")
        return content, False

    if m:
        insert_pos = m.end(1)
        content = content[:insert_pos] + "".join(entries) + content[insert_pos:]
    else:
        marker = "const RAW = {"
        idx = content.index(marker)
        insert_pos = idx + len(marker)
        block = "\n    '%s': [\n%s    ],\n" % (today_iso, "".join(entries))
        content = content[:insert_pos] + block + content[insert_pos:]

    return content, True


def main():
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    today_iso = now.strftime("%Y-%m-%d")
    today_date = now.date()

    all_items = []
    for url, source in FEEDS:
        try:
            all_items.extend(fetch_items(url, source))
        except Exception as e:
            print(f"[경고] {source} 피드를 가져오지 못했습니다: {e}", file=sys.stderr)

    if not all_items:
        print("두 피드 모두 가져오지 못해 오늘은 업데이트를 건너뜁니다.")
        return

    changed_any = False
    for path in REPO_FILES:
        try:
            new_content, changed = update_file(path, today_iso, today_date, all_items)
        except FileNotFoundError:
            print(f"[경고] {path} 파일을 찾을 수 없습니다.", file=sys.stderr)
            continue
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            changed_any = True
            print(f"[{path}] 업데이트 완료")

    if not changed_any:
        print("변경된 내용이 없습니다.")


if __name__ == "__main__":
    main()
