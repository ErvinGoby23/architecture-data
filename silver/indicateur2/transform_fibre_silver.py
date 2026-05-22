"""
silver_fibre.py — Pipeline Silver · Indicateur 2 : Score de connectivité (Pilier Fixe)
Urban Data Explorer

Source  : brute/Score de connectivité/indicateur-wifi.csv  (ARCEP, T4 2025)
Output  :
    silver/Score de connectivité/fibre_paris_silver.parquet
    PostgreSQL  → silver.fibre_paris
    MongoDB     → urban_data.fibre_paris

Table silver produite :
    code_arrondissement     int     ex: 75101
    nom_arrondissement      str     ex: "Paris 1er Arrondissement"
    nb_logements            int
    nb_etablissements       int
    locaux_total            int     meilleure estimation ARCEP T4 2025
    locaux_fibres_T4_2025   int     locaux raccordés fibre T4 2025
    code_postal             int     ex: 75001

Usage :
    python silver_fibre.py
"""

import pandas as pd
import os

# ── Chemins & config ───────────────────────────────────────────────────────
BRONZE_FILE = '../../brute/Score de connectivité/indicateur-wifi.csv'
SILVER_DIR  = '../../silver/Score de connectivité/'

os.makedirs(SILVER_DIR, exist_ok=True)

# ── 1. Chargement ──────────────────────────────────────────────────────────
# header=4 : le CSV ARCEP a 4 lignes de métadonnées avant les vrais headers
df = pd.read_csv(BRONZE_FILE, sep=None, engine='python', header=4, encoding='latin-1')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f'[1/4] Chargement OK — shape brut : {df.shape}')

# ── 2. Filtre Paris (75101 → 75120) ────────────────────────────────────────
df = df[df['Code arrondissement'].between(75101, 75120)].copy()
print(f'[2/4] Filtrage Paris — lignes retenues : {len(df)} (attendu : 20)')

# ── 3. Nettoyage colonnes numériques ───────────────────────────────────────
cols_numeriques = ['Logements', 'Établissements',
                   'Meilleure estimation des locaux T4 2025'] + \
                  [c for c in df.columns if c.startswith('T')]

for col in cols_numeriques:
    if col in df.columns:
        df[col] = (df[col].astype(str)
                          .str.replace('\u202f', '', regex=False)
                          .str.replace('\xa0',   '', regex=False)
                          .str.replace(' ',      '', regex=False)
                          .str.strip())
        df[col] = pd.to_numeric(df[col], errors='coerce')

assert df.isnull().sum().sum() == 0, '⚠️  Valeurs manquantes détectées !'
print('[3/4] Nettoyage OK — 0 valeur manquante')

# ── 4. Construction table silver ───────────────────────────────────────────
df_silver = df[['Code arrondissement', 'Nom arrondissement',
                'Logements', 'Établissements',
                'Meilleure estimation des locaux T4 2025',
                'T4 2025']].copy()

df_silver.columns = ['code_arrondissement', 'nom_arrondissement',
                     'nb_logements', 'nb_etablissements',
                     'locaux_total', 'locaux_fibres_T4_2025']

# Code postal (donnée administrative directe)
df_silver['code_postal'] = df_silver['code_arrondissement'] - 75100 + 75000

df_silver = df_silver.sort_values('code_arrondissement').reset_index(drop=True)
print(f'[4/4] Table silver construite — shape : {df_silver.shape}')

# ── Export CSV ─────────────────────────────────────────────────────────────
csv_path = SILVER_DIR + 'fibre_paris_silver.csv'
df_silver.to_csv(csv_path, index=False, encoding='utf-8-sig')
print(f'✓ CSV : {csv_path}')

print('\n=== SILVER fibre OK ===')
print(df_silver.to_string(index=False))
