import pandas as pd
import requests
import time
from io import StringIO
from pathlib import Path

CANONICAL_COLS = [
    "league", "date", "home_team", "away_team", "home_goals", "away_goals",
    "ht_home_goals", "ht_away_goals", "home_shots", "away_shots",
    "home_target", "away_target", "home_fouls", "away_fouls",
    "home_corners", "away_corners", "home_yellow", "away_yellow",
    "home_red", "away_red", "home_xg", "away_xg", "source",
]

# SADECE 60 liginden football-data.co.uk'da olanlar
# new/ = tek dosya (tum sezonlar), mmz4281/ = sezonluk
# DUZELTME (2026-09): usa/aut/jap icin football-data.co.uk SEZON BAZLI dosya
# YAYINLAMIYOR - sadece tek konsolide 'new/' dosyasi var. mmz4281/ formati bu
# 3 lig icin her calistirmada sessizce 404 donduruyordu (workflow yesil gorunuyordu
# ama hicbir veri cekilmiyordu) - bu yuzden 21 aydir guncellenmemislerdi.
FD_MAP = {
    'usa': 'new/USA.csv',
    'aut': 'new/AUT.csv',
    'jap': 'new/JPN.csv',
    'chn': 'new/CHN.csv',
    'e0': 'mmz4281/{season}/E0.csv',
    'e1': 'mmz4281/{season}/E1.csv',
    'e2': 'mmz4281/{season}/E2.csv',
    'e3': 'mmz4281/{season}/E3.csv',
    'ec': 'mmz4281/{season}/EC.csv',
    'd1': 'mmz4281/{season}/D1.csv',
    'd2': 'mmz4281/{season}/D2.csv',
    'sp1': 'mmz4281/{season}/SP1.csv',
    'sp2': 'mmz4281/{season}/SP2.csv',
    'i1': 'mmz4281/{season}/I1.csv',
    'i2': 'mmz4281/{season}/I2.csv',
    'f1': 'mmz4281/{season}/F1.csv',
    'f2': 'mmz4281/{season}/F2.csv',
    'n1': 'mmz4281/{season}/N1.csv',
    'p1': 'mmz4281/{season}/P1.csv',
    'g1': 'mmz4281/{season}/G1.csv',
    't1': 'mmz4281/{season}/T1.csv',
    'b1': 'mmz4281/{season}/B1.csv',
    'sc0': 'mmz4281/{season}/SC0.csv',
    'sc1': 'mmz4281/{season}/SC1.csv',
    'sc2': 'mmz4281/{season}/SC2.csv',
    'sc3': 'mmz4281/{season}/SC3.csv',
}

SEASONS = ['2526', '2627']
BASE_URL = 'https://www.football-data.co.uk/'


def norm(t):
    return str(t).strip().lower()


def fetch(url):
    for i in range(3):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception:
            time.sleep(2)
    return None


def _get_col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series([pd.NA] * len(df), index=df.index)


def proc(df, code):
    # DUZELTME (2026-09-20): football-data.co.uk'nin "ekstra ligler" (new/
    # klasoru: USA/AUT/JPN/CHN) dosyalari ANA liglerden FARKLI sutun isimleri
    # kullaniyor - HomeTeam/AwayTeam/FTHG/FTAG yerine Home/Away/HG/AG. Bu
    # yuzden bu 4 ligde takim/skor hep BOS kaliyordu (sadece tarih+lig
    # eklenmis oluyordu). Asagida HER IKI sema da destekleniyor. Bu format
    # sut/korner/kart sutunu ICERMEZ, o yuzden bu liglerde korner/kart
    # tahmini icin veri hala eksik kalacak (ayri bir API-Football backfill
    # gerekir) - bu script sadece skor/tarihi tazeler.
    df['date'] = _get_col(df, 'Date')
    df['home_team'] = _get_col(df, 'HomeTeam', 'Home')
    df['away_team'] = _get_col(df, 'AwayTeam', 'Away')
    df['home_goals'] = _get_col(df, 'FTHG', 'HG')
    df['away_goals'] = _get_col(df, 'FTAG', 'AG')
    df['ht_home_goals'] = _get_col(df, 'HTHG')
    df['ht_away_goals'] = _get_col(df, 'HTAG')
    df['home_shots'] = _get_col(df, 'HS')
    df['away_shots'] = _get_col(df, 'AS')
    df['home_target'] = _get_col(df, 'HST')
    df['away_target'] = _get_col(df, 'AST')
    df['home_fouls'] = _get_col(df, 'HF')
    df['away_fouls'] = _get_col(df, 'AF')
    df['home_corners'] = _get_col(df, 'HC')
    df['away_corners'] = _get_col(df, 'AC')
    df['home_yellow'] = _get_col(df, 'HY')
    df['away_yellow'] = _get_col(df, 'AY')
    df['home_red'] = _get_col(df, 'HR')
    df['away_red'] = _get_col(df, 'AR')
    df['league'] = code
    df['source'] = 'football-data.co.uk'
    df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
    for c in CANONICAL_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    return df[CANONICAL_COLS].copy()


def main():
    # 60 lig listesini master CSV'den oku
    try:
        master = pd.read_csv('merged_2024_2025_2026_v3.csv', encoding='utf-8-sig', low_memory=False)
        leagues_60 = set(master['league'].dropna().astype(str).str.strip().str.lower().unique())
    except Exception:
        leagues_60 = set(FD_MAP.keys())

    p = Path('gaps_output/merged_gaps.csv')
    p.parent.mkdir(exist_ok=True)

    if p.exists():
        gaps = pd.read_csv(p, encoding='utf-8-sig', low_memory=False)
    else:
        gaps = pd.DataFrame(columns=CANONICAL_COLS)

    gaps['date'] = pd.to_datetime(gaps['date'], errors='coerce', dayfirst=True)
    gaps = gaps.reindex(columns=CANONICAL_COLS).copy()

    keys = set()
    for _, r in gaps.iterrows():
        if pd.notna(r['date']):
            keys.add((r['date'].strftime('%Y-%m-%d'), norm(r['home_team']), norm(r['away_team'])))

    total = 0

    for lig_code, path_template in FD_MAP.items():
        if lig_code not in leagues_60:
            continue

        if '{season}' in path_template:
            for season in SEASONS:
                url = BASE_URL + path_template.format(season=season)
                print(f'[{lig_code}-{season}] cekiliyor...')
                resp = fetch(url)
                if resp is None:
                    print('  404/hata')
                    continue
                try:
                    df = proc(pd.read_csv(StringIO(resp.text), encoding='utf-8-sig', low_memory=False), lig_code)
                    nr = []
                    for _, r in df.iterrows():
                        if pd.isna(r['date']):
                            continue
                        k = (r['date'].strftime('%Y-%m-%d'), norm(r['home_team']), norm(r['away_team']))
                        if k not in keys:
                            nr.append(r.to_dict())
                            keys.add(k)
                    if nr:
                        gaps = pd.concat([gaps, pd.DataFrame(nr)], ignore_index=True)
                        total += len(nr)
                        print(f'  +{len(nr)}')
                    else:
                        print('  0')
                except Exception as e:
                    print(f'  HATA: {e}')
        else:
            url = BASE_URL + path_template
            print(f'[{lig_code}] cekiliyor...')
            resp = fetch(url)
            if resp is None:
                print('  404/hata')
                continue
            try:
                df = proc(pd.read_csv(StringIO(resp.text), encoding='utf-8-sig', low_memory=False), lig_code)
                nr = []
                for _, r in df.iterrows():
                    if pd.isna(r['date']):
                        continue
                    k = (r['date'].strftime('%Y-%m-%d'), norm(r['home_team']), norm(r['away_team']))
                    if k not in keys:
                        nr.append(r.to_dict())
                        keys.add(k)
                if nr:
                    gaps = pd.concat([gaps, pd.DataFrame(nr)], ignore_index=True)
                    total += len(nr)
                    print(f'  +{len(nr)}')
                else:
                    print('  0')
            except Exception as e:
                print(f'  HATA: {e}')

    gaps = gaps.sort_values('date').reset_index(drop=True)
    gaps.to_csv(p, index=False, encoding='utf-8-sig')
    print(f'\nTAMAM. Yeni: {total}, Toplam: {len(gaps)}')


if __name__ == '__main__':
    main()
