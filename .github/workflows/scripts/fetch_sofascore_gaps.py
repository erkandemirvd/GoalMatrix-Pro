# ANAHTAR GEREKTIRMEZ. ESPN'de olmayan 12 lig icin Sofascore'un acik verisi.
# Yer: .github/workflows/scripts/fetch_sofascore_gaps.py
import sys
import time
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_footballdata_gaps as fd  # noqa: E402

fd.ALIAS.update({})
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "application/json", "Referer": "https://www.sofascore.com/", "Origin": "https://www.sofascore.com"}
API = "https://api.sofascore.com/api/v1"
LOG = []
MAX_STATS = 400

# master lig adi -> (Sofascore ulke, turnuva adi ipuclari, saat dilimi)
T = {
    "croatia-prva-hnl": ("Croatia", ["hnl", "supersport"], "Europe/Zagreb"),
    "serbia-superliga": ("Serbia", ["super liga", "superliga"], "Europe/Belgrade"),
    "lithuania-a-lyga": ("Lithuania", ["a lyga"], "Europe/Vilnius"),
    "cameroon-elite-one": ("Cameroon", ["elite one"], "Africa/Douala"),
    "iceland-urvalsdeild": ("Iceland", ["besta", "urvalsdeild", "úrvalsdeild"], "Atlantic/Reykjavik"),
    "iceland-1-deild": ("Iceland", ["1. deild", "lengjudeild"], "Atlantic/Reykjavik"),
    "finland-ykkonen": ("Finland", ["ykkönen", "ykkonen"], "Europe/Helsinki"),
    "republic-of-ireland-first-divis": ("Ireland", ["first division"], "Europe/Dublin"),
    "bulgaria-first-league": ("Bulgaria", ["first league", "parva"], "Europe/Sofia"),
    "hungary-nb-i": ("Hungary", ["nb i"], "Europe/Budapest"),
    "latvia-virsliga": ("Latvia", ["virsliga"], "Europe/Riga"),
    "canada-canadian-premier-league": ("Canada", ["canadian premier"], "America/Toronto"),
}
BAD = ["women", "cup", "u19", "u21", "u20", "u18", "reserve", "playoff", "play-off", "relegation", "ii", "youth", "w "]


def say(m):
    print(m)
    LOG.append(str(m))


def get(url):
    for i in range(2):
        try:
            r = requests.get(url, headers=H, timeout=20)
            if r.status_code == 200:
                return r.json()
            say(f"  HTTP {r.status_code} {url.replace(API, '')}")
            if r.status_code in (403, 404):
                return None
            time.sleep(5)
        except Exception as e:  # noqa
            say(f"  HATA {type(e).__name__} {str(e)[:100]}")
            time.sleep(3)
    return None


def pick(ev):
    tn = ev.get("tournament", {})
    ut = tn.get("uniqueTournament", {}) or {}
    cat = (tn.get("category", {}) or {}).get("name", "")
    name = (ut.get("name") or tn.get("name") or "")
    low = name.lower()
    for slug, (country, hints, tz) in T.items():
        if cat == country and any(h in low for h in hints) and not any(b in low for b in BAD):
            return slug, tz
    return None, None


def stats(eid):
    j = get(f"{API}/event/{eid}/statistics")
    out = {}
    if not j:
        return out
    m = {"total shots": "shots", "shots on target": "target", "corner kicks": "corners",
         "fouls": "fouls", "yellow cards": "yellow", "red cards": "red"}
    for per in j.get("statistics", []):
        if per.get("period") != "ALL":
            continue
        for g in per.get("groups", []):
            for it in g.get("statisticsItems", []):
                k = m.get(str(it.get("name", "")).lower())
                if k:
                    try:
                        out[f"home_{k}"] = float(it["homeValue"])
                        out[f"away_{k}"] = float(it["awayValue"])
                    except (KeyError, TypeError, ValueError):
                        pass
    return out


def main():
    fd.OUT.mkdir(exist_ok=True)
    master = pd.read_csv(fd.MASTER, encoding="utf-8-sig", low_memory=False)
    master["date"] = pd.to_datetime(master["date"], format="%Y-%m-%d", errors="coerce")
    master = master.dropna(subset=["date"])
    gaps = pd.read_csv(fd.GAPS, encoding="utf-8-sig", low_memory=False) if fd.GAPS.exists() else pd.DataFrame(columns=fd.CANONICAL_COLS)
    gaps["date"] = pd.to_datetime(gaps["date"], format="%Y-%m-%d", errors="coerce")
    gaps = gaps.dropna(subset=["date"]).reindex(columns=fd.CANONICAL_COLS)
    canon = fd.Canon(master)
    existing = pd.concat([master[["league", "date", "home_team", "away_team"]],
                          gaps[["league", "date", "home_team", "away_team"]]], ignore_index=True)
    keys, pair, busy = fd.load_keys(existing)
    last = existing.groupby("league").date.max().to_dict()
    today = pd.Timestamp(_date.today())
    start = min(max(fd.START, last.get(s, fd.START) - timedelta(days=2)) for s in T)
    start = max(start, today - timedelta(days=130))

    seen_t, added, newrows = {}, 0, []
    d = start
    ok = 0
    while d <= today:
        j = get(f"{API}/sport/football/scheduled-events/{d:%Y-%m-%d}")
        if j is None:
            if ok == 0:
                break
            d += timedelta(days=1)
            continue
        ok += 1
        for ev in j.get("events", []):
            tn = ev.get("tournament", {})
            cat = (tn.get("category", {}) or {}).get("name", "")
            if cat in {v[0] for v in T.values()}:
                seen_t[(cat, (tn.get("uniqueTournament", {}) or {}).get("name") or tn.get("name"))] = 1
            slug, tz = pick(ev)
            if not slug or ev.get("status", {}).get("type") != "finished":
                continue
            try:
                gh, ga = int(ev["homeScore"]["current"]), int(ev["awayScore"]["current"])
            except (KeyError, TypeError, ValueError):
                continue
            dt = datetime.fromtimestamp(ev["startTimestamp"], timezone.utc).astimezone(ZoneInfo(tz))
            dd = pd.Timestamp(dt.date())
            if not (fd.START <= dd <= today) or dd <= last.get(slug, fd.START) - timedelta(days=2):
                continue
            hn, an = ev["homeTeam"]["name"], ev["awayTeam"]["name"]
            h, a = canon(slug, hn), canon(slug, an)
            if (slug, hn) in canon.unmapped or (slug, an) in canon.unmapped:
                continue
            ds = dd.strftime("%Y-%m-%d")
            if (slug, ds, h, a) in keys or any(abs((x - dd).days) <= 1 for x in pair.get((slug, h, a), [])):
                continue
            if (slug, ds, h) in busy or (slug, ds, a) in busy:
                continue
            row = {c: np.nan for c in fd.CANONICAL_COLS}
            row.update(league=slug, date=dd, home_team=h, away_team=a, home_goals=gh, away_goals=ga,
                       ht_home_goals=ev.get("homeScore", {}).get("period1", np.nan),
                       ht_away_goals=ev.get("awayScore", {}).get("period1", np.nan), source="sofascore")
            newrows.append((row, ev["id"]))
            keys.add((slug, ds, h, a))
            pair.setdefault((slug, h, a), []).append(dd)
            pair.setdefault((slug, a, h), []).append(dd)
            busy.add((slug, ds, h))
            busy.add((slug, ds, a))
        d += timedelta(days=1)
        time.sleep(0.4)

    (fd.OUT / "sofascore_turnuvalar.txt").write_text(
        "\n".join(f"{a}\t{b}" for a, b in sorted(seen_t)), encoding="utf-8")
    n_stat = 0
    rows = []
    for row, eid in sorted(newrows, key=lambda x: x[0]["date"], reverse=True):
        if n_stat < MAX_STATS:
            s = stats(eid)
            time.sleep(0.3)
            if s:
                row.update(s)
                n_stat += 1
        rows.append(row)
    if rows:
        new = pd.DataFrame(rows)[fd.CANONICAL_COLS]
        gaps = pd.concat([gaps, new], ignore_index=True)
    gaps = gaps.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    gaps["date"] = pd.to_datetime(gaps["date"]).dt.strftime("%Y-%m-%d")
    gaps.to_csv(fd.GAPS, index=False, encoding="utf-8-sig")
    per = pd.DataFrame(rows).groupby("league").size().to_dict() if rows else {}
    say(f"TAMAM. Sofascore: gun={ok}, yeni mac={len(rows)}, istatistik={n_stat}, ligler={per}")
    if canon.unmapped:
        say("ESLESMEYEN TAKIMLAR: " + "; ".join(f"{l}:{t}" for l, t in sorted(canon.unmapped)))
    (fd.OUT / "sofascore_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    if ok == 0:
        print("::error::Sofascore erisilemedi")
        sys.exit(1)


if __name__ == "__main__":
    main()
