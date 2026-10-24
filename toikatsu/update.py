"""Fetch the official Toikatsu timetables and write data.json for the page.

Run by .github/workflows/toikatsu.yml. dojos.json holds the fixed store list
(name, address, coordinates); everything that changes comes from the official site.
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://tkdj.info/dojo/timetable?dojo={}"
JST = timezone(timedelta(hours=9))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (toikatsu-now)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def classes(page):
    m = re.search(r'"(\d+)":\{"id":\1,"dojo_id"', page)
    start = page.rfind("{", 0, m.start())
    obj, _ = json.JSONDecoder().raw_decode(page[start:])
    return obj


def text(fragment):
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(x.strip() for x in t.split("\n") if x.strip())


def notes(page):
    """Notice boxes under 注意事項, e.g. holiday hours."""
    out = []
    i = page.find("注意事項")
    if i < 0:
        return out
    section = page[i:page.find("インストラクタープロフィール", i)]
    for title, body in re.findall(r"<strong>(.*?)</strong>(.*?)</div>", section, re.S):
        title, body = text(title), text(body)
        if re.search(r"祝|休|営業|変更|年末|年始|臨時", title + body):
            out.append({"t": re.sub(r"^\W+", "", title), "b": body})
    return out


def hours(page):
    m = re.search(r"営業時間</[^>]+>\s*(?:<[^>]+>\s*)*([^<]+)", page)
    return text(m.group(1)) if m else ""


def main():
    dojos = json.load(open(os.path.join(HERE, "dojos.json"), encoding="utf-8"))
    rows, extra, failed = [], {}, []
    for did, d in dojos.items():
        try:
            page = fetch(URL.format(did))
            for c in classes(page).values():
                if not c.get("active"):
                    continue
                name = html.unescape(c["name"]).replace("\n", " ").replace("　", " ").strip()
                rows.append([int(did), c["day"], c["open_time"][:5], c["close_time"][:5], name,
                             c["grade"], c["strength"], c["trial"], c.get("canceled_dt")])
            month = re.search(r"(\d+)月時間割", page)
            extra[did] = {"notes": notes(page), "hours": hours(page), "month": month.group(1) if month else ""}
        except Exception as e:
            failed.append(did)
            print("failed", did, d["n"], e, file=sys.stderr)
        time.sleep(0.5)
    if len(failed) > len(dojos) // 2:
        sys.exit("too many stores failed; keeping the previous data")
    old = {}
    path = os.path.join(HERE, "data.json")
    if failed and os.path.exists(path):
        old = json.load(open(path, encoding="utf-8"))
        # keep the last good rows for stores that failed this time
        rows += [r for r in old.get("c", []) if str(r[0]) in failed]
        for did in failed:
            if did in old.get("x", {}):
                extra[did] = old["x"][did]
    out = {"updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
           "dojos": {k: {**v, "u": URL.format(k)} for k, v in dojos.items()},
           "x": extra, "c": rows}
    new = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    prev = json.dumps({**old, "updated": out["updated"]}, ensure_ascii=False, separators=(",", ":")) if old else None
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print("stores", len(dojos) - len(failed), "classes", len(rows), "canceled",
          sum(1 for r in rows if r[8]))


if __name__ == "__main__":
    main()
