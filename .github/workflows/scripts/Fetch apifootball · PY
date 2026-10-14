# fetch_apifootball.py
# Yer: .github/workflows/scripts/fetch_apifootball.py  (fetch_footballdata_gaps.py ile ayni klasor)
#
# football-data.co.uk'ta OLMAYAN 20 ligi API-Football'dan ceker:
#   Cek, Hirvatistan, Sirbistan, Sili, Kolombiya, Litvanya, Kamerun, Izlanda x2, Finlandiya x2,
#   Norvec 1. Lig, Irlanda 1. Lig, Bulgaristan, Macaristan, Letonya, Ekvador, Kanada,
#   Brezilya Serie B, Isvec Superettan.
#
# Gunluk istek siniri (varsayilan 95) asilmaz:
#   1) Once her lig icin tek istekle biten maclar cekilir (skor + ilk yari).
#   2) Kalan istek hakki, istatistigi (sut, korner, faul, kart, xG) olmayan maclara harcanir,
#      EN YENI mactan baslayarak. Kalanlar ertesi gun devam eder.
# Tarih: ligin kendi saatine gore (timezone parametresi), kayma olmasin diye.
# Anahtar: GitHub > Settings > Secrets > Actions > API_FOOTBALL_KEY
import json
import os
import sys
import time
from datetime import date as _date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_footballdata_gaps as fd  # noqa: E402  (norm, Canon, load_keys, sabitler)

API = "https://v3.football.api-sports.io"
STATE = fd.OUT / "api_state.json"
BUDGET = int(os.environ.get("API_DAILY_BUDGET", "95"))
KEY = os.environ.get("API_FOOTBALL_KEY", "")

# ana CSV lig adi -> (ulke, [lig adi ipuclari], saat dilimi)
TARGETS = {
    "czech-republic-first-league": ("Czech-Republic", ["Czech Liga", "First League"], "Europe/Prague"),
    "croatia-prva-hnl": ("Croatia", ["HNL", "1. HNL", "Prva HNL"], "Europe/Zagreb"),
    "serbia-superliga": ("Serbia", ["Super Liga", "SuperLiga"], "Europe/Belgrade"),
    "chile-primera-division": ("Chile", ["Primera Division"], "America/Santiago"),
    "colombia-categoria-primera-a": ("Colombia", ["Primera A", "Liga BetPlay"], "America/Bogota"),
    "lithuania-a-lyga": ("Lithuania", ["A Lyga"], "Europe/Vilnius"),
    "cameroon-elite-one": ("Cameroon", ["Elite One"], "Africa/Douala"),
    "iceland-urvalsdeild": ("Iceland", ["Urvalsdeild", "Besta deild"], "Atlantic/Reykjavik"),
    "iceland-1-deild": ("Iceland", ["1. Deild", "Lengjudeild"], "Atlantic/Reykjavik"),
    "finland-ykkosliiga": ("Finland", ["Ykkosliiga"], "Europe/Helsinki"),
    "finland-ykkonen": ("Finland", ["Ykkonen"], "Europe/Helsinki"),
    "norway-first-division": ("Norway", ["1. Division", "OBOS-ligaen"], "Europe/Oslo"),
    "republic-of-ireland-first-divis": ("Ireland", ["First Division"], "Europe/Dublin"),
    "bulgaria-first-league": ("Bulgaria", ["First League", "Parva Liga"], "Europe/Sofia"),
    "hungary-nb-i": ("Hungary", ["NB I"], "Europe/Budapest"),
    "latvia-virsliga": ("Latvia", ["Virsliga"], "Europe/Riga"),
    "ecuador-primera-categoria-serie": ("Ecuador", ["Liga Pro", "Serie A"], "America/Guayaquil"),
    "canada-canadian-premier-league": ("Canada", ["Canadian Premier League"], "America/Toronto"),
    "brazil-serie-b": ("Brazil", ["Serie B"], "America/Sao_Paulo"),
    "sweden-superettan": ("Sweden", ["Superettan"], "Europe/Stockholm"),
}
# lig adi bulunamazsa elle id yazilabilir: {"cameroon-elite-one": 411}
LEAGUE_ID_OVERRIDE = {}

STAT_MAP = {"Total Shots": "shots", "Shots on Goal": "target", "Fouls": "fouls",
            "Corner Kicks": "corners", "Yellow Cards": "yellow", "Red Cards": "red",
            "expected_goals": "xg"}


class Budget:
    def __init__(self, n):
        self.left = n
        self.used = 0
        self.stop_reason = None

    def call(self, path, params):
        if self.left <= 0:
            return None
        self.left -= 1
        self.used += 1
        for i in range(2):
            try:
                r = requests.get(API + path, params=params, headers={"x-apisports-key": KEY}, timeout=30)
                if r.status_code == 429:
                    time.sleep(10)
                    continue
                r.raise_for_status()
                j = r.json()
                err = j.get("errors")
                if err:
                    msg = json.dumps(err, ensure_ascii=False)[:200]
                    print("  API hata:", msg)
                    if "rate" in msg.lower() or "limit" in msg.lower() or "request" in msg.lower():
                        self.left = 0
                        self.stop_reason = msg
                    return None
                return j
            except Exception as e:  # noqa
                print("  istek hatasi", path, str(e)[:80])
                time.sleep(3)
        return None


def pick_league(resp, hints):
    """Cevaptaki liglerden 'League' tipinde ve adi ipucuna uyani sec; (id, sezon) don."""
    hn = [fd.norm(h) for h in hints]
    best = None
    for item in resp:
        lg = item.get("league", {})
        if lg.get("type") != "League":
            continue
        n = fd.norm(lg.get("name", ""))
        score = 2 if n in hn else (1 if any(h and (h in n or n in h) for h in hn) else 0)
        if score and (best is None or score > best[0]):
            seasons = item.get("seasons", [])
            cur = [s for s in seasons if s.get("current")]
            s = cur[0] if cur else (max(seasons, key=lambda x: x.get("year", 0)) if seasons else None)
            if s:
                best = (score, lg["id"], s["year"], lg.get("name"))
    return best


def stat_row(resp, home_id):
    out = {}
    for side in resp:
        pre = "home" if side["team"]["id"] == home_id else "away"
        for st in side.get("statistics", []):
            k = STAT_MAP.get(st.get("type"))
            if not k:
                continue
            v = st.get("value")
            try:
                v = float(str(v).replace("%", "")) if v is not None else np.nan
            except ValueError:
                v = np.nan
            out[f"{pre}_{k}"] = v
    return out


def main():
    if not KEY:
        print("::error::API_FOOTBALL_KEY tanimli degil (GitHub Secrets).")
        sys.exit(1)
    fd.OUT.mkdir(exist_ok=True)
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
    state.setdefault("leagues", {})
    state.setdefault("fixtures", {})
    canon = fd.Canon(master)
    existing = pd.concat([master[["league", "date", "home_team", "away_team"]],
                          gaps[["league", "date", "home_team", "away_team"]]], ignore_index=True)
    keys, pair, busy = fd.load_keys(existing)
    last = existing.groupby("league").date.max().to_dict()
    today = pd.Timestamp(_date.today())
    b = Budget(BUDGET)
    errors, added = [], []

    # ---------- 1) biten maclar ----------
    for slug, (country, hints, tz) in TARGETS.items():
        lid = LEAGUE_ID_OVERRIDE.get(slug)
        info = state["leagues"].get(slug)
        stale = info is not None and (today - pd.Timestamp(info.get("checked", "2000-01-01"))).days > 20
        if info is None or stale or (lid and info.get("id") != lid):
            if lid:
                j = b.call("/leagues", {"id": lid})
                if j and j["response"]:
                    seasons = j["response"][0].get("seasons", [])
                    cur = [s for s in seasons if s.get("current")]
                    s = cur[0] if cur else max(seasons, key=lambda x: x["year"])
                    info = {"id": lid, "season": s["year"], "name": j["response"][0]["league"]["name"]}
            else:
                j = b.call("/leagues", {"country": country})
                pick = pick_league(j["response"], hints) if j else None
                if pick:
                    info = {"id": pick[1], "season": pick[2], "name": pick[3]}
            if info:
                info["checked"] = today.strftime("%Y-%m-%d")
                state["leagues"][slug] = info
                print(f"[{slug}] lig bulundu: {info['name']} (id {info['id']}, sezon {info['season']})")
            else:
                errors.append(f"{slug}: lig bulunamadi (ulke {country}, ipucu {hints})")
                continue
        start = max(last.get(slug, fd.START), fd.START) - timedelta(days=2)
        j = b.call("/fixtures", {"league": info["id"], "season": info["season"],
                                 "from": start.strftime("%Y-%m-%d"), "to": today.strftime("%Y-%m-%d"),
                                 "status": "FT-AET-PEN", "timezone": tz})
        if j is None:
            if b.left > 0:
                errors.append(f"{slug}: maclar cekilemedi")
            continue
        n = 0
        for fx in j["response"]:
            gh, ga = fx["goals"]["home"], fx["goals"]["away"]
            if gh is None or ga is None:
                continue
            d = pd.Timestamp(fx["fixture"]["date"][:10])
            if not (fd.START <= d <= today):
                continue
            h = canon(slug, fx["teams"]["home"]["name"])
            a = canon(slug, fx["teams"]["away"]["name"])
            ds = d.strftime("%Y-%m-%d")
            fid = str(fx["fixture"]["id"])
            st = state["fixtures"].get(fid)
            if (slug, ds, h, a) in keys or any(abs((x - d).days) <= 1 for x in pair.get((slug, h, a), [])):
                continue
            if (slug, ds, h) in busy or (slug, ds, a) in busy:
                continue
            ht = fx.get("score", {}).get("halftime", {}) or {}
            row = {c: np.nan for c in fd.CANONICAL_COLS}
            row.update(league=slug, date=d, home_team=h, away_team=a, home_goals=gh, away_goals=ga,
                       ht_home_goals=ht.get("home"), ht_away_goals=ht.get("away"), source="api-football")
            added.append(row)
            state["fixtures"][fid] = {"league": slug, "date": ds, "home": h, "away": a,
                                      "home_id": fx["teams"]["home"]["id"], "stats": 0, "tries": 0}
            keys.add((slug, ds, h, a))
            pair.setdefault((slug, h, a), []).append(d)
            pair.setdefault((slug, a, h), []).append(d)
            busy.add((slug, ds, h))
            busy.add((slug, ds, a))
            n += 1
        print(f"[{slug}] +{n} mac")
    if added:
        new = pd.DataFrame(added)[fd.CANONICAL_COLS]
        gaps = pd.concat([gaps, new], ignore_index=True) if len(gaps) else new

    # ---------- 2) istatistik (kalan hakla, en yeni once) ----------
    gaps["date"] = pd.to_datetime(gaps["date"])
    idx = {(r.league, r.date.strftime("%Y-%m-%d"), r.home_team, r.away_team): i
           for i, r in zip(gaps.index, gaps.itertuples(index=False))}
    queue = sorted([(v["date"], fid) for fid, v in state["fixtures"].items()
                    if v["stats"] == 0 and v["tries"] < 4], reverse=True)
    n_stat = 0
    for _, fid in queue:
        if b.left <= 0:
            break
        v = state["fixtures"][fid]
        j = b.call("/fixtures/statistics", {"fixture": fid})
        if j is None:
            continue
        v["tries"] += 1
        i = idx.get((v["league"], v["date"], v["home"], v["away"]))
        if not j["response"] or i is None:
            continue
        for k, val in stat_row(j["response"], v["home_id"]).items():
            gaps.at[i, k] = val
        v["stats"] = 1
        n_stat += 1
    remaining = sum(1 for v in state["fixtures"].values() if v["stats"] == 0 and v["tries"] < 4)

    gaps = gaps.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    gaps["date"] = gaps["date"].dt.strftime("%Y-%m-%d")
    gaps.to_csv(fd.GAPS, index=False, encoding="utf-8-sig")
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if canon.unmapped:
        pd.DataFrame(sorted(canon.unmapped), columns=["league", "takim"]).to_csv(
            fd.UNMAPPED.with_name("eslesmeyen_takimlar_api.csv"), index=False, encoding="utf-8-sig")
    print(f"\nTAMAM. Yeni mac: {len(added)}, istatistigi alinan: {n_stat}, istatistigi bekleyen: {remaining}, "
          f"kullanilan istek: {b.used}/{BUDGET}, eslesmeyen takim: {len(canon.unmapped)}, hata: {len(errors)}")
    for e in errors:
        print("::error::" + e)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
