name: Eksik Lig Verilerini Cek

permissions:
  contents: write

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests pandas numpy
      - name: football-data.co.uk (38 lig)
        run: python .github/workflows/scripts/fetch_footballdata_gaps.py
      - name: ESPN (eski kalan ligler)
        if: always()
        continue-on-error: true
        run: python .github/workflows/scripts/fetch_espn_gaps.py
      - name: Tam sezon + oran verisi
        if: always()
        continue-on-error: true
        run: python .github/workflows/fd_tam_cek.py
      - name: Commit ve push
        if: always()
        run: |
          git config user.email "action@github.com"
          git config user.name "GitHub Action"
          git add gaps_output/
          git diff --cached --quiet || git commit -m "Veriler guncellendi"
          git pull --rebase
          git push
