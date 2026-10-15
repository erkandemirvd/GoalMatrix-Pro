# fetch_espn.py   (ANAHTAR GEREKTIRMEZ)
# Yer: .github/workflows/scripts/fetch_espn.py  (fetch_footballdata_gaps.py ile ayni klasor)
#
# football-data.co.uk'ta olmayan ligleri ESPN'in herkese acik verisinden ceker.
#   1) Her lig icin son bilinen tarihten bugune biten maclar (skor + ilk yari).
#   2) Her maci ayri ayri sorarak istatistik (sut, isabetli sut, korner, faul, kart).
#      Calisma basina en fazla MAX_STATS mac; en yeniden eskiye, kalanlar ertesi gun.
# Bir lig ESPN'de bulunamazsa ya da adi beklenen lige uymazsa ATLANIR ve gunluge
# "ATLANDI" yazilir (yanlis ligi dosyaya karistirmamak icin).
# Tarihler ligin yerel saatine gore yazilir.
import json
import sys
import time
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_footballdata_gaps as fd  # noqa: E402  (norm, Canon, load_keys, sabitler)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STATE = fd.OUT / "espn_state.json"
MAX_STATS = 400
UA = {"User-Agent": "Mozilla/5.0 (GoalMatrixESPN/1.0)"}

# ana CSV lig adi -> (ESPN lig kodu adaylari, beklenen ad ipuclari, saat dilimi)
# ESPN'den donen lig adi ipuclarindan birini icermiyorsa lig atlanir.
TARGETS = {
    "czech-republic-first-league": (["cze.1"], ["czech"], "Europe/Prague"),
    "croatia-prva-hnl": (["cro.1"], ["croatian", "hnl"], "Europe/Zagreb"),
    "serbia-superliga": (["srb.1"], ["serbian", "super liga", "superliga"], "Europe/Belgrade"),
    "chile-primera-division": (["chi.1"], ["chilean", "primera"], "America/Santiago"),
    "colombia-categoria-primera-a": (["col.1"], ["colombian", "primera a", "betplay"], "America/Bogota"),
    "lithuania-a-lyga": (["ltu.1"], ["lithuanian", "a lyga"], "Europe/Vilnius"),
    "cameroon-elite-one": (["cmr.1"], ["cameroon", "elite"], "Africa/Douala"),
    "iceland-urvalsdeild": (["isl.1"], ["besta", "urvals", "icelandic"], "Atlantic/Reykjavik"),
    "iceland-1-deild": (["isl.2"], ["lengju", "1. deild", "first division", "division 1"], "Atlantic/Reykjavik"),
    "finland-ykkosliiga": (["fin.2"], ["ykk"], "Europe/Helsinki"),
    "finland-ykkonen": (["fin.3"], ["ykk"], "Europe/Helsinki"),
    "norway-first-division": (["nor.2"], ["obos", "1. div", "first div", "division 1"], "Europe/Oslo"),
    "republic-of-ireland-first-divis": (["irl.2"], ["first division"], "Europe/Dublin"),
    "bulgaria-first-league": (["bul.1"], ["bulgarian", "parva", "first"], "Europe/Sofia"),
    "hungary-nb-i": (["hun.1"], ["hungarian", "nb i"], "Europe/Budapest"),
    "latvia-virsliga": (["lva.1", "lat.1"], ["latvian", "virsliga"], "Europe/Riga"),
    "ecuador-primera-categoria-serie": (["ecu.1"], ["ecuador", "liga pro", "serie a"], "America/Guayaquil"),
    "canada-canadian-premier-league": (["can.1"], ["canadian premier"], "America/Toronto"),
    "brazil-serie-b": (["bra.2"], ["serie b"], "America/Sao_Paulo"),
    "sweden-superettan": (["swe.2"], ["superettan"], "Europe/Stockholm"),
}

STAT_NAMES = {  # ESPN istatistik adi (kucuk harf) -> bizim sutun
    "totalshots": "shots", "shots": "shots",
    "shotsontarget": "target", "shotsongoal": "target",
    "foulscommitted": "fouls", "fouls": "fouls",
    "woncorners": "corners", "cornerkicks": "corners", "corners": "corners",
    "yellowcards": "yellow", "redcards": "red",
}


LOG = []


def say(msg):
    print(msg)
    LOG.append(str(msg))


HOSTS = ["https://site.api.espn.com/apis/site/v2/sports/soccer",
         "https://site.web.api.espn.com/apis/site/v2/sports/soccer"]


def get_json(url, params=None):
    urls = [url] + [url.replace(BASE, h) for h in HOSTS if h != BASE]
    for u in urls:
        for i in range(2):
            try:
                r = requests.get(u, params=params, headers=UA, timeout=20)
                if r.status_code in (400, 404):
                    if len(LOG) < 60:
                        say(f"  HTTP {r.status_code} {u.split('/soccer/')[1]} {params}")
                    break
                if r.status_code == 429:
                    time.sleep(10 * (i + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa
                if len(LOG) < 60:
                    say(f"  HATA {u.split('/soccer/')[1]}: {type(e).__name__} {str(e)[:150]}")
                time.sleep(2)
    return None


def _day_list(d, e):
    out = []
    while d <= e:
        out.append(d)
        d += timedelta(days=1)
    return out


def scoreboard(slug, start, end):
    """[start, end] araligindaki biten maclar. Once aralik, olmazsa 14 gun, olmazsa gun gun."""
    out, seen = [], set()
    league_name = None
    url = f"{BASE}/{slug}/scoreboard"

    def add(j):
        nonlocal league_name
        lg = (j.get("leagues") or [{}])[0]
        league_name = lg.get("name") or league_name
        for ev in j.get("events", []):
            if ev["id"] not in seen:
                seen.add(ev["id"])
                out.append(ev)

    # 1) tek istek: aralik, limit'siz
    j = get_json(url, {"dates": f"{start:%Y%m%d}-{end:%Y%m%d}"})
    if j is not None:
        add(j)
        if out:
            return out, league_name
    # 2) tek gunluk istekler (en saglam bicim). Lig hic yanit vermezse hemen vazgec.
    days = _day_list(start, end)
    ok = 0
    for k, d in enumerate(days):
        j = get_json(url, {"dates": f"{d:%Y%m%d}"})
        if j is None:
            if k == 2 and ok == 0:
                return None, league_name
            continue
        ok += 1
        add(j)
        time.sleep(0.15)
    if ok == 0:
        return None, league_name
    return out, league_name


def lig_listesi():
    """ESPN'deki gercek futbol lig kodlari -> gaps_output/espn_ligler.txt (bir kez)."""
    f = fd.OUT / "espn_ligler.txt"
    if f.exists():
        return
    try:
        r = requests.get("https://sports.core.api.espn.com/v2/sports/soccer/leagues",
                         params={"limit": 1000}, headers=UA, timeout=30)
        say(f"lig listesi HTTP {r.status_code}")
        items = r.json().get("items", [])
    except Exception as e:  # noqa
        say(f"lig listesi HATA {type(e).__name__} {str(e)[:100]}")
        return
    rows = []
    for it in items:
        ref = it.get("$ref", "")
        slug = ref.split("/leagues/")[-1].split("?")[0]
        try:
            j = requests.get(ref.replace("http://", "https://"), headers=UA, timeout=10).json()
            rows.append(f"{slug}\t{j.get('name', '')}")
        except Exception:  # noqa
            rows.append(f"{slug}\t?")
        time.sleep(0.05)
    f.write_text("\n".join(rows), encoding="utf-8")
    say(f"lig listesi yazildi: {len(rows)} lig")


def parse_event(ev, tz):
    st = ev.get("status", {}).get("type", {})
    if not st.get("completed"):
        return None
    comp = ev["competitions"][0]
    h = next((c for c in comp["competitors"] if c.get("homeAway") == "home"), None)
    a = next((c for c in comp["competitors"] if c.get("homeAway") == "away"), None)
    if not h or not a:
        return None
    try:
        gh, ga = int(h["score"]), int(a["score"])
    except (KeyError, ValueError, TypeError):
        return None
    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ZoneInfo(tz))

    def ht(c):
        ls = c.get("linescores") or []
        try:
            return float(ls[0]["value"]) if ls else np.nan
        except (KeyError, ValueError, TypeError):
            return np.nan
    return {"id": str(ev["id"]), "date": pd.Timestamp(dt.date()),
            "home": h["team"].get("displayName") or h["team"].get("name"),
            "away": a["team"].get("displayName") or a["team"].get("name"),
            "home_id": str(h["team"].get("id")), "gh": gh, "ga": ga, "hth": ht(h), "hta": ht(a)}


def stat_values(summary, home_id):
    out = {}
    for t in (summary.get("boxscore") or {}).get("teams", []):
        pre = "home" if str(t.get("team", {}).get("id")) == home_id else "away"
        for s in t.get("statistics", []):
            key = STAT_NAMES.get(str(s.get("name", "")).replace(" ", "").lower())
            if not key:
                continue
            try:
                out[f"{pre}_{key}"] = float(s.get("displayValue"))
            except (TypeError, ValueError):
                pass
    return out


def main():
    fd.OUT.mkdir(exist_ok=True)
    lig_listesi()
    master = pd.read_csv(fd.MASTER, encoding="utf-8-sig", low_memory=False)
    master["date"] = pd.to_datetime(master["date"], format="%Y-%m-%d", errors="coerce")
    master = master.dropna(subset=["date"])
    if fd.GAPS.exists():
        gaps = pd.read_csv(fd.GAPS, encoding="utf-8-sig", low_memory=False)
        gaps["date"] = pd.to_datetime(gaps["date"], format="%Y-%m-%d", errors="coerce")
        gaps = gaps.dropna(subset=["date"]).reindex(columns=fd.CANONICAL_COLS)
    else:
        gaps = pd.DataFrame(columns=fd.CANONICAL_COLS)
        gaps["date"] = pd.to_datetime(gaps["date"])
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    state.setdefault("fixtures", {})
    canon = fd.Canon(master)
    existing = pd.concat([master[["league", "date", "home_team", "away_team"]],
                          gaps[["league", "date", "home_team", "away_team"]]], ignore_index=True)
    keys, pair, busy = fd.load_keys(existing)
    last = existing.groupby("league").date.max().to_dict()
    today = pd.Timestamp(_date.today())

    added, found, skipped = [], [], []
    for slug, (cands, hints, tz) in TARGETS.items():
        # her seferinde en az 150 gun geriye bak (eslesmeyen takim yuzunden atlanan maclar sonra gelsin)
        start = max(fd.START, min(last.get(slug, fd.START) - timedelta(days=2),
                                  today - timedelta(days=150))).to_pydatetime()
        evs, espn_slug, lname = None, None, None
        for c in cands:
            evs, lname = scoreboard(c, start, today.to_pydatetime())
            if evs is not None:
                espn_slug = c
                break
        if evs is None:
            skipped.append(slug)
            say(f"[{slug}] ATLANDI: ESPN'de bulunamadi ({', '.join(cands)})")
            continue
        if not any(h in (lname or "").lower() for h in hints):
            skipped.append(slug)
            say(f"[{slug}] ATLANDI: ESPN lig adi beklenenle uyusmuyor -> '{lname}' ({espn_slug})")
            continue
        n = 0
        n_unm = 0
        for ev in evs:
            p = parse_event(ev, tz)
            if p is None or not (fd.START <= p["date"] <= today):
                continue
            h, a = canon(slug, p["home"]), canon(slug, p["away"])
            if (slug, p["home"]) in canon.unmapped or (slug, p["away"]) in canon.unmapped:
                n_unm += 1          # takim adi ana dosyadakiyle eslesmedi: yeni yazim acmamak icin ATLA
                continue
            ds = p["date"].strftime("%Y-%m-%d")
            if (slug, ds, h, a) in keys or any(abs((x - p["date"]).days) <= 1
                                               for x in pair.get((slug, h, a), [])):
                continue
            if (slug, ds, h) in busy or (slug, ds, a) in busy:
                continue
            row = {c: np.nan for c in fd.CANONICAL_COLS}
            row.update(league=slug, date=p["date"], home_team=h, away_team=a,
                       home_goals=p["gh"], away_goals=p["ga"],
                       ht_home_goals=p["hth"], ht_away_goals=p["hta"], source="espn")
            added.append(row)
            state["fixtures"][p["id"]] = {"league": slug, "espn": espn_slug, "date": ds, "home": h,
                                          "away": a, "home_id": p["home_id"], "stats": 0, "tries": 0}
            keys.add((slug, ds, h, a))
            pair.setdefault((slug, h, a), []).append(p["date"])
            pair.setdefault((slug, a, h), []).append(p["date"])
            busy.add((slug, ds, h))
            busy.add((slug, ds, a))
            n += 1
        found.append(slug)
        print(f"[{slug}] ESPN '{lname}' ({espn_slug}): +{n} mac" + (f", {n_unm} mac takim adi eslesmedigi icin atlandi" if n_unm else ""))

    if added:
        new = pd.DataFrame(added)[fd.CANONICAL_COLS]
        gaps = pd.concat([gaps, new], ignore_index=True) if len(gaps) else new

    # ---- istatistikler (en yeni mactan baslayarak) ----
    gaps["date"] = pd.to_datetime(gaps["date"])
    idx = {(r.league, r.date.strftime("%Y-%m-%d"), r.home_team, r.away_team): i
           for i, r in zip(gaps.index, gaps.itertuples(index=False))}
    queue = sorted([(v["date"], k) for k, v in state["fixtures"].items()
                    if v["stats"] == 0 and v["tries"] < 3], reverse=True)[:MAX_STATS]
    n_stat = 0
    for _, eid in queue:
        v = state["fixtures"][eid]
        j = get_json(f"{BASE}/{v['espn']}/summary", {"event": eid})
        time.sleep(0.25)
        v["tries"] += 1
        i = idx.get((v["league"], v["date"], v["home"], v["away"]))
        if j is None or i is None:
            continue
        vals = stat_values(j, v["home_id"])
        if not vals:
            continue
        for k, val in vals.items():
            gaps.at[i, k] = val
        v["stats"] = 1
        n_stat += 1
    waiting = sum(1 for v in state["fixtures"].values() if v["stats"] == 0 and v["tries"] < 3)

    gaps = gaps.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    gaps["date"] = gaps["date"].dt.strftime("%Y-%m-%d")
    gaps.to_csv(fd.GAPS, index=False, encoding="utf-8-sig")
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if canon.unmapped:
        import difflib
        rows = []
        for lg, t in sorted(canon.unmapped):
            pool = sorted(set(master[master.league == lg].home_team) | set(master[master.league == lg].away_team))
            best = max(pool, key=lambda n: difflib.SequenceMatcher(None, fd.norm(t), fd.norm(n)).ratio(), default="")
            r = difflib.SequenceMatcher(None, fd.norm(t), fd.norm(best)).ratio() if best else 0
            rows.append((lg, t, best, round(r, 2)))
        pd.DataFrame(rows, columns=["league", "espn_adi", "en_yakin_ana_dosya_adi", "benzerlik"]).to_csv(
            fd.OUT / "eslesmeyen_takimlar_espn.csv", index=False, encoding="utf-8-sig")
    print(f"\nTAMAM. Bulunan lig: {len(found)}/{len(TARGETS)}, yeni mac: {len(added)}, "
          f"istatistigi alinan: {n_stat}, bekleyen: {waiting}, eslesmeyen takim: {len(canon.unmapped)}")
    if skipped:
        print("ATLANAN LIGLER:", ", ".join(skipped))
    (fd.OUT / "espn_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    if not found:
        print("::error::Hic lig bulunamadi (ESPN erisimi veya adres degismis olabilir)")
        sys.exit(1)


if __name__ == "__main__":
    main()
