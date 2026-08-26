import os, requests, pandas as pd
from io import StringIO

# 60 ligin kodları ve isimleri
LIGLER = {
    'E0': 'Ingiltere Premier', 'E1': 'Ingiltere Championship', 'E2': 'Ingiltere League 1',
    'E3': 'Ingiltere League 2', 'EC': 'Ingiltere Conference', 'EFL Cup': 'Ingiltere Lig Kupasi',
    'SC0': 'Iskocya Premiership', 'SC1': 'Iskocya Championship', 'SC2': 'Iskocya League 1',
    'SC3': 'Iskocya League 2',
    'D1': 'Almanya Bundesliga', 'D2': 'Almanya 2. Bundesliga',
    'I1': 'Italya Serie A', 'I2': 'Italya Serie B',
    'SP1': 'Ispanya LaLiga', 'SP2': 'Ispanya LaLiga2',
    'F1': 'Fransa Ligue 1', 'F2': 'Fransa Ligue 2',
    'N1': 'Hollanda Eredivisie', 'B1': 'Belcika Pro League',
    'P1': 'Portekiz Primeira Liga', 'T1': 'Turkiye Super Lig',
    'G1': 'Yunanistan Super League', 'ARG': 'Arjantin', 'AUT': 'Avusturya',
    'CHN': 'Cin', 'JAP': 'Japonya', 'USA': 'ABD MLS',
    'BRA': 'Brezilya Serie A', 'BRA2': 'Brezilya Serie B',
    'BUL': 'Bulgaristan', 'CAM': 'Kamerun', 'CAN': 'Kanada',
    'CHL': 'Sili', 'COL': 'Kolombiya', 'CRO': 'Hirvatistan',
    'CZE': 'Cekya', 'DEN': 'Danimarka', 'ECU': 'Ekvador',
    'FIN': 'Finlandiya', 'FIN2': 'Finlandiya Ykkonen', 'FIN3': 'Finlandiya Ykkosliiga',
    'HUN': 'Macaristan', 'ICE': 'Izlanda', 'ICE2': 'Izlanda 1. Deild',
    'LAT': 'Letonya', 'LIT': 'Litvanya', 'MEX': 'Meksika',
    'NOR': 'Norvec', 'NOR2': 'Norvec 1. Division',
    'POL': 'Polonya', 'IRL': 'Irlanda', 'IRL2': 'Irlanda 1. Division',
    'ROM': 'Romanya', 'RUS': 'Rusya', 'SRB': 'Sirbistan',
    'SWE': 'Isvec', 'SWE2': 'Isvec Superettan', 'SWE3': 'Isvec Svenska Cupen',
    'SUI': 'Isvicre'
}

# 3 sezon çek: geçmiş boşlukları da doldur
SEZONLAR = ['2425', '2526', '2627']
ADRES = "https://www.football-data.co.uk/mmz4281/{s}/{l}.csv"
CIKTI = "gaps_output/merged_gaps.csv"

os.makedirs("gaps_output", exist_ok=True)
tablolar = []

for sezon in SEZONLAR:
    for kod, isim in LIGLER.items():
        url = ADRES.format(s=sezon, l=kod)
        try:
            yanit = requests.get(url, timeout=30)
            if yanit.status_code == 200:
                df = pd.read_csv(StringIO(yanit.text), low_memory=False)
                df['lig'] = isim
                df['sezon'] = f"20{sezon[:2]}-20{sezon[2:]}"
                tablolar.append(df)
                print(f"Tamam {isim} {sezon}")
            else:
                print(f"Atla {isim} {sezon} HTTP {yanit.status_code}")
        except Exception as hata:
            print(f"Hata {isim} {sezon}: {hata}")

if tablolar:
    birlesik = pd.concat(tablolar, ignore_index=True)
    cevir = {'Date':'date','HomeTeam':'home_team','AwayTeam':'away_team',
             'FTHG':'home_goals','FTAG':'away_goals','HTHG':'ht_home_goals','HTAG':'ht_away_goals',
             'HS':'home_shots','AS':'away_shots','HST':'home_target','AST':'away_target',
             'HF':'home_fouls','AF':'away_fouls','HC':'home_corners','AC':'away_corners',
             'HY':'home_yellow','AY':'away_yellow','HR':'home_red','AR':'away_red'}
    birlesik = birlesik.rename(columns={k:v for k,v in cevir.items() if k in birlesik.columns})
    birlesik.to_csv(CIKTI, index=False, encoding='utf-8-sig')
    print(f"\nKaydedildi: {len(birlesik)} mac")
else:
    print("Veri yok!")
