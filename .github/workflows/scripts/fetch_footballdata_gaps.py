# fetch_footballdata_gaps.py  (DUZELTILMIS SURUM)
# Yer: .github/workflows/scripts/fetch_footballdata_gaps.py
#
# football-data.co.uk'tan biten maclari ceker, ana CSV'deki yazimla (lig + takim adi)
# eslestirir, gaps_output/merged_gaps.csv dosyasina ekler.
#
# ESKI SURUMDEN FARKLAR
#  1) TARIH HATASI: eski script gaps CSV'yi ISO tarihle (2026-03-06) yazip sonra
#     dayfirst=True ile geri okuyordu -> gun/ay yer degistiriyordu (2026-06-03),
#     gunu 12'den buyuk olanlar bos (NaT) oluyordu. Artik tarih her yerde sabit format.
#  2) RUS/IRL/NOR/SWE/POL/ROU/BRA/MEX/DNK/FIN/SWZ/ARG de cekilir ve ana CSV'deki
#     uzun lig adina (mexico-liga-mx ...) cevrilir. Eskiden ayri "lig" gibi kaliyordu.
#  3) Takim adlari ana CSV'deki yazima cevrilir. Eslesmeyenler
#     gaps_output/eslesmeyen_takimlar.csv dosyasina yazilir (sessizce yeni takim acilmaz).
#  4) 404/hata sessizce gecilmez: ozet basilir, hata varsa cikis kodu 1.
#  5) Ayni mac +-1 gun kaymayla, ters ev/dep ile veya ayni takim ayni gun iki macla
#     tekrar eklenmez.
#  6) Negatif / sahte sifir istatistikler bos birakilir.
import re
import sys
import time
import unicodedata
import difflib
from datetime import date as _date
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE_URL = "https://www.football-data.co.uk/"
MASTER = "merged_58lig_temiz.csv"          # ana CSV (repo kokunde)
OUT = Path("gaps_output")
GAPS = OUT / "merged_gaps.csv"
UNMAPPED = OUT / "eslesmeyen_takimlar.csv"
SEASONS = ["2425", "2526", "2627"]
START = pd.Timestamp("2024-01-01")
UA = {"User-Agent": "Mozilla/5.0 (GoalMatrixFD/3.0)"}

CANONICAL_COLS = [
    "league", "date", "home_team", "away_team", "home_goals", "away_goals",
    "ht_home_goals", "ht_away_goals", "home_shots", "away_shots",
    "home_target", "away_target", "home_fouls", "away_fouls",
    "home_corners", "away_corners", "home_yellow", "away_yellow",
    "home_red", "away_red", "home_xg", "away_xg", "source",
]

# kod -> (adres, ana CSV'deki lig adi)
M = "mmz4281/{season}/"
LEAGUES = {
    "e0": (M + "E0.csv", "e0"), "e1": (M + "E1.csv", "e1"), "e2": (M + "E2.csv", "e2"),
    "e3": (M + "E3.csv", "e3"), "ec": (M + "EC.csv", "ec"),
    "sc0": (M + "SC0.csv", "scotland-premiership"), "sc1": (M + "SC1.csv", "sc1"),
    "sc2": (M + "SC2.csv", "sc2"), "sc3": (M + "SC3.csv", "sc3"),
    "d1": (M + "D1.csv", "d1"), "d2": (M + "D2.csv", "d2"),
    "i1": (M + "I1.csv", "i1"), "i2": (M + "I2.csv", "i2"),
    "sp1": (M + "SP1.csv", "sp1"), "sp2": (M + "SP2.csv", "sp2"),
    "f1": (M + "F1.csv", "f1"), "f2": (M + "F2.csv", "f2"),
    "n1": (M + "N1.csv", "n1"), "b1": (M + "B1.csv", "b1"), "p1": (M + "P1.csv", "p1"),
    "t1": (M + "T1.csv", "t1"), "g1": (M + "G1.csv", "g1"),
    # tek dosyali "new/" ligler (tum sezonlar bir dosyada)
    "usa": ("new/USA.csv", "usa"), "aut": ("new/AUT.csv", "aut"),
    "jap": ("new/JPN.csv", "jap"), "chn": ("new/CHN.csv", "chn"),
    "arg": ("new/ARG.csv", "arg"),
    "rus": ("new/RUS.csv", "russia-russian-premier-league"),
    "irl": ("new/IRL.csv", "republic-of-ireland-premier-div"),
    "nor": ("new/NOR.csv", "norway-eliteserien"),
    "swe": ("new/SWE.csv", "sweden-allsvenskan"),
    "pol": ("new/POL.csv", "poland-ekstraklasa"),
    "rou": ("new/ROU.csv", "romania-liga-i"),
    "bra": ("new/BRA.csv", "brazil-serie-a"),
    "mex": ("new/MEX.csv", "mexico-liga-mx"),
    "dnk": ("new/DNK.csv", "denmark-superliga"),
    "fin": ("new/FIN.csv", "finland-veikkausliiga"),
    "swz": ("new/SWZ.csv", "switzerland-super-league"),
}

# Ayni kulubun bilinen farkli yazimlari (ana CSV'deki yazima)
ALIAS = {
    "Rodina Moscow": "Rodina Moskva", "Spartak Moscow": "Spartak Moskva",
    "Dynamo Moscow": "Dinamo Moskva", "FC Copenhagen": "København",
    "Poli Iasi": "CSM Iaşi", "Univ. Craiova": "CS U Craiova",
    "Real Betis": "Betis", "Dundee Utd": "Dundee United",
    "BSC Young Boys": "Young Boys", "Lausanne": "Lausanne Sport",
    "Grasshoppers": "Grasshopper", "Zurich": "Zürich",
    "Club Tijuana": "Tijuana", "Guadalajara Chivas": "Guadalajara",
    "UNAM Pumas": "U.N.A.M. - Pumas", "Atl. San Luis": "Atlético San Luis",
    "Athletico-PR": "Atlético PR", "Botafogo RJ": "Botafogo", "Flamengo RJ": "Flamengo",
    "Vasco": "Vasco da Gama", "Bodo/Glimt": "FK Bodo - Glimt", "KFUM Oslo": "KFUM",
    "St. Patricks": "St Patrick's Athl.",
}


def norm(s):
    s = str(s)
    for a, b in {"ß": "ss", "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "æ": "ae"}.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|fk|sk|if|bk|afc|cf|sc|ac|as|ca|cd|cs|club|de|da|do)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def parse_date(s):
    """football-data tarihleri gun/ay/yil: dd/mm/YYYY veya dd/mm/yy. Baska bicim yok."""
    s = s.astype(str).str.strip()
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    return d.fillna(pd.to_datetime(s, format="%d/%m/%y", errors="coerce"))


def fetch(url):
    for i in range(3):
        try:
            time.sleep(2)
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 404:
                return None, "404"
            if r.status_code == 429:
                time.sleep(20 * (i + 1))
                continue
            r.raise_for_status()
            try:
                return r.content.decode("utf-8-sig"), "ok"
            except UnicodeDecodeError:
                return r.content.decode("cp1252", errors="replace"), "ok"
        except Exception as e:  # noqa
            err = str(e)[:80]
            time.sleep(4)
    return None, locals().get("err", "hata")


def col(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return pd.Series([np.nan] * len(df), index=df.index)


def proc(raw, league):
    df = raw.loc[:, ~raw.columns.astype(str).str.startswith("Unnamed")].copy()
    o = pd.DataFrame(index=df.index)
    o["date"] = parse_date(col(df, "Date"))
    o["home_team"] = col(df, "HomeTeam", "Home").astype(str).str.strip()
    o["away_team"] = col(df, "AwayTeam", "Away").astype(str).str.strip()
    names = {"home_goals": ("FTHG", "HG"), "away_goals": ("FTAG", "AG"),
             "ht_home_goals": ("HTHG",), "ht_away_goals": ("HTAG",),
             "home_shots": ("HS",), "away_shots": ("AS",), "home_target": ("HST",),
             "away_target": ("AST",), "home_fouls": ("HF",), "away_fouls": ("AF",),
             "home_corners": ("HC",), "away_corners": ("AC",), "home_yellow": ("HY",),
             "away_yellow": ("AY",), "home_red": ("HR",), "away_red": ("AR",)}
    for k, v in names.items():
        o[k] = pd.to_numeric(col(df, *v), errors="coerce")
    o["home_xg"] = np.nan
    o["away_xg"] = np.nan
    o["league"] = league
    o["source"] = "football-data.co.uk"
    o = o.dropna(subset=["date", "home_goals", "away_goals"])
    o = o[(o.home_team != "nan") & (o.away_team != "nan")]
    # eksik veri temizligi
    num = ["home_shots", "away_shots", "home_target", "away_target", "home_fouls", "away_fouls",
           "home_corners", "away_corners", "home_yellow", "away_yellow", "home_red", "away_red"]
    o[num] = o[num].mask(o[num] < 0)
    for a, b in [("home_shots", "away_shots"), ("home_target", "away_target"),
                 ("home_fouls", "away_fouls"), ("home_corners", "away_corners"),
                 ("home_yellow", "away_yellow"), ("home_red", "away_red")]:
        m = o[a].isna() | o[b].isna()
        o.loc[m, [a, b]] = np.nan
    m = (o.home_shots == 0) & (o.away_shots == 0)
    o.loc[m, ["home_shots", "away_shots", "home_target", "away_target"]] = np.nan
    m = (o.home_corners == 0) & (o.away_corners == 0)
    o.loc[m, ["home_corners", "away_corners"]] = np.nan
    m = (o.home_target > o.home_shots) | (o.away_target > o.away_shots)
    o.loc[m, ["home_target", "away_target"]] = np.nan
    return o[CANONICAL_COLS]


class Canon:
    def __init__(self, master):
        self.names = {}
        if master is not None:
            for lg, g in master.groupby("league"):
                ns = set(g.home_team) | set(g.away_team)
                self.names[lg] = {norm(n): n for n in ns}
        self.unmapped = set()

    def __call__(self, league, team):
        pool = self.names.get(league)
        if not pool:
            return team
        if team in pool.values():
            return team
        if team in ALIAS and ALIAS[team] in pool.values():
            return ALIAS[team]
        k = norm(team)
        if k in pool:
            return pool[k]
        c = difflib.get_close_matches(k, list(pool), 1, 0.9)
        if c:
            return pool[c[0]]
        sub = [n for kk, n in pool.items() if len(k) >= 5 and len(kk) >= 5 and (k in kk or kk in k)]
        if len(sub) == 1:                      # Drogheda -> Drogheda United gibi
            return sub[0]
        self.unmapped.add((league, team))
        return team


def load_keys(df):
    keys, pair, busy = set(), {}, set()
    for lg, d, h, a in zip(df.league, df.date, df.home_team, df.away_team):
        ds = d.strftime("%Y-%m-%d")
        keys.add((lg, ds, h, a))
        pair.setdefault((lg, h, a), []).append(d)
        pair.setdefault((lg, a, h), []).append(d)      # ters ev/dep
        busy.add((lg, ds, h))
        busy.add((lg, ds, a))
    return keys, pair, busy


def main():
    OUT.mkdir(exist_ok=True)
    master = None
    if Path(MASTER).exists():
        master = pd.read_csv(MASTER, encoding="utf-8-sig", low_memory=False)
        master["date"] = pd.to_datetime(master["date"], format="%Y-%m-%d", errors="coerce")
        master = master.dropna(subset=["date"])
    else:
        print(f"UYARI: {MASTER} yok, takim adi eslestirmesi yapilmayacak")
    canon = Canon(master)

    if GAPS.exists():
        gaps = pd.read_csv(GAPS, encoding="utf-8-sig", low_memory=False)
        gaps["date"] = pd.to_datetime(gaps["date"], format="%Y-%m-%d", errors="coerce")  # ISO, dayfirst YOK
        gaps = gaps.dropna(subset=["date"]).reindex(columns=CANONICAL_COLS)
    else:
        gaps = pd.DataFrame(columns=CANONICAL_COLS)
        gaps["date"] = pd.to_datetime(gaps["date"])

    existing = pd.concat([x[["league", "date", "home_team", "away_team"]]
                          for x in (master, gaps) if x is not None and len(x)], ignore_index=True)
    keys, pair, busy = load_keys(existing) if len(existing) else (set(), {}, set())

    today = pd.Timestamp(_date.today())
    added, errors, report = [], [], []
    for code, (tmpl, league) in LEAGUES.items():
        jobs = [tmpl.format(season=s) for s in SEASONS] if "{season}" in tmpl else [tmpl]
        n_add = 0
        for path in jobs:
            text, status = fetch(BASE_URL + path)
            if text is None:
                # yeni sezon dosyasi henuz yoksa (404) normal sayilir, ama new/ dosyasi 404 olamaz
                if path.startswith("new/") or status != "404":
                    errors.append(f"{code} {path}: {status}")
                    print(f"  HATA {code} {path}: {status}")
                continue
            try:
                df = proc(pd.read_csv(StringIO(text), low_memory=False, on_bad_lines="skip"), league)
            except Exception as e:  # noqa
                errors.append(f"{code} {path}: okunamadi {e}")
                continue
            df = df[(df.date >= START) & (df.date <= today)]
            for r in df.itertuples(index=False):
                h, a = canon(league, r.home_team), canon(league, r.away_team)
                ds = r.date.strftime("%Y-%m-%d")
                if (league, ds, h, a) in keys:
                    continue
                if any(abs((x - r.date).days) <= 1 for x in pair.get((league, h, a), [])):
                    continue
                if (league, ds, h) in busy or (league, ds, a) in busy:
                    continue
                row = r._asdict()
                row["home_team"], row["away_team"] = h, a
                added.append(row)
                keys.add((league, ds, h, a))
                pair.setdefault((league, h, a), []).append(r.date)
                pair.setdefault((league, a, h), []).append(r.date)
                busy.add((league, ds, h))
                busy.add((league, ds, a))
                n_add += 1
        report.append((code, n_add))
        print(f"[{code}] +{n_add}")

    if added:
        new = pd.DataFrame(added)[CANONICAL_COLS]
        gaps = pd.concat([gaps, new], ignore_index=True) if len(gaps) else new
    gaps = gaps.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    gaps["date"] = pd.to_datetime(gaps["date"]).dt.strftime("%Y-%m-%d")
    gaps.to_csv(GAPS, index=False, encoding="utf-8-sig")

    if canon.unmapped:
        pd.DataFrame(sorted(canon.unmapped), columns=["league", "takim"]).to_csv(
            UNMAPPED, index=False, encoding="utf-8-sig")
    print(f"\nTAMAM. Yeni mac: {len(added)}, gaps toplam: {len(gaps)}, "
          f"eslesmeyen takim: {len(canon.unmapped)}, hata: {len(errors)}")
    for e in errors:
        print("::error::" + e)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
