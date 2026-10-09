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
      - run: pip install requests pandas
      - run: python .github/workflows/scripts/fetch_footballdata_gaps.py
      - name: Tam sezon + oran verisi
        continue-on-error: true
        run: python .github/workflows/fd_tam_cek.py
      - run: |
          git config user.email "action@github.com"
          git config user.name "GitHub Action"
          git add gaps_output/
          git diff --cached --quiet || git commit -m "Veriler guncellendi"
          git push
