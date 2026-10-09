# fd_tam_cek.py  -- GitHub Actions'ta calisir (scripts/ icine koy)
# football-data.co.uk'tan TAM sezon dosyalarini ceker: tarih AYRISTIRMASI KESIN
# (gun/ay/yil), istatistik + O/U 2.5 oranlari (varsa) korunur.
# Cikti: gaps_output/fd_full.csv
import re, sys, time
from io import StringIO
from pathlib import Path
import numpy as np, pandas as pd, requests

OUT = Path("gaps_output"); OUT.mkdir(exist_ok=True)
MAIN = ["E0","E1","E2","E3","EC","SC0","SC1","SC2","SC3","D1","D2","I1","I2",
        "SP1","SP2","F1","F2","N1","B1","P1","T1","G1"]
EXTRA = ["USA","AUT","JPN","ARG","BRA","CHN","DNK","FIN","IRL","MEX","NOR","POL","ROU","RUS","SWE","SWZ"]
SEASONS = ["2425","2526","2627"]
UA = {"User-Agent": "Mozilla/5.0 (GoalMatrixFD/2.0)"}
MAP = {"Date":"date","HomeTeam":"home_team","AwayTeam":"away_team","FTHG":"home_goals","FTAG":"away_goals",
       "HTHG":"ht_home_goals","HTAG":"ht_away_goals","HS":"home_shots","AS":"away_shots","HST":"home_target",
       "AST":"away_target","HF":"home_fouls","AF":"away_fouls","HC":"home_corners","AC":"away_corners",
       "HY":"home_yellow","AY":"away_yellow","HR":"home_red","AR":"away_red",
       # extra lig dosyalari (tek dosya) farkli adlar kullanir
       "Home":"home_team","Away":"away_team","HG":"home_goals","AG":"away_goals"}
ODDS_RE = re.compile(r"^[A-Za-z0-9]+[<>]2\.5$")

def parse_date(s):
    s = s.astype(str).str.strip()
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")          # dd/mm/yyyy
    return d.fillna(pd.to_datetime(s, format="%d/%m/%y", errors="coerce"))  # dd/mm/yy

def get(url, tries=3):
    for i in range(tries):
        try:
            time.sleep(3)
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 404: return None
            if r.status_code == 429: time.sleep(30*(i+1)); continue
            r.raise_for_status()
            return r.content.decode("cp1252", errors="ignore")
        except Exception as e:
            print("  hata", url, e); time.sleep(5)
    return None

def prepare(text, code, season):
    df = pd.read_csv(StringIO(text), on_bad_lines="skip", low_memory=False)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    disc = [c for c in df.columns if "3.5" in str(c) or "BTTS" in str(c).upper()]
    if disc: print("  [KESIF] 3.5/BTTS sutunlari:", disc)
    odds = [c for c in df.columns if ODDS_RE.match(str(c))]
    keep = {k: v for k, v in MAP.items() if k in df.columns}
    out = df[list(keep) + odds].rename(columns=keep)
    out["date"] = parse_date(out["date"])
    out = out.dropna(subset=["date","home_team","away_team","home_goals","away_goals"])
    out.insert(0, "season", season); out.insert(0, "code", code)
    return out

def main():
    parts = []
    jobs = [(c, s, f"https://www.football-data.co.uk/mmz4281/{s}/{c}.csv") for c in MAIN for s in SEASONS]
    jobs += [(c, "all", f"https://www.football-data.co.uk/new/{c}.csv") for c in EXTRA]
    for code, season, url in jobs:
        print("Cekiliyor:", code, season)
        t = get(url)
        if t is None: print("  yok/atlandi"); continue
        p = prepare(t, code, season)
        if code in EXTRA: p = p[p["date"] >= "2024-01-01"]
        if len(p): parts.append(p); print(f"  {len(p)} mac, {p['date'].min().date()} -> {p['date'].max().date()}")
    if not parts: print("Veri yok."); sys.exit(0)
    res = pd.concat(parts, ignore_index=True).sort_values("date")
    res["date"] = res["date"].dt.strftime("%Y-%m-%d")
    res.to_csv(OUT / "fd_full.csv", index=False, encoding="utf-8-sig")
    print("TOPLAM", len(res), "->", OUT / "fd_full.csv")

if __name__ == "__main__":
    main()
