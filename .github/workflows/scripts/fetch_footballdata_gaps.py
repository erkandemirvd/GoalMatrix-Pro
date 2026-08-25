import os, requests, pandas as pd
from io import StringIO

LIGLER = {'P1':'Portekiz','F2':'Fransa L2','N1':'Hollanda','SP2':'Ispanya LaLiga2','T1':'Turkiye','E0':'Ingiltere','B1':'Belcika'}
SEZONLAR = ['2526','2627']
ADRES = "https://www.football-data.co.uk/mmz4281/{s}/{l}.csv"
CIKTI = "gaps_output/merged_gaps.csv"

os.makedirs("gaps_output", exist_ok=True)
tablolar = []

for sezon in SEZONLAR:
    for kod,isim in LIGLER.items():
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
                print(f"Atla {isim} {sezon}")
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
