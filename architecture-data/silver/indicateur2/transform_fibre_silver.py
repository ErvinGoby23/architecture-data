"""
transform_fibre_silver.py — Pipeline Silver · Indicateur 2 : Fibre
Urban Data Explorer

Source  : brute/Score-de-connectivite/indicateur-wifi.csv  (ARCEP, T4 2025)
Output  : nettoyage-indicateur2/fibre_paris_silver.parquet
"""

import pandas as pd
import os
import sys
from datetime import datetime
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

BRONZE_FILE = '../../brute/Score-de-connectivite/indicateur-wifi.csv'
SILVER_DIR = os.path.join('nettoyage-indicateur2', date_str)

os.makedirs(SILVER_DIR, exist_ok=True)

# -- Chargement -----------------------------------------------------------
df = pd.read_csv(
    BRONZE_FILE,
    sep=None,
    engine='python',
    header=4,
    encoding='utf-8-sig'
)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f'[1/4] Chargement OK — shape brut : {df.shape}')
print("Voici les colonnes du fichier :", df.columns.tolist())
# -- Filtrage Paris -------------------------------------------------------
df = df[df['Code arrondissement'].between(75101, 75120)].copy()
print(f'[2/4] Filtrage Paris — lignes retenues : {len(df)} (attendu : 20)')

# -- Nettoyage vectorisé — lambda sur toutes les colonnes numériques ------
cols_numeriques = (
    ['Logements', 'Établissements', 'Meilleure estimation des locaux T4 2025'] +
    [c for c in df.columns if c.startswith('T')]
)

# Lambda de nettoyage appliquée sur chaque colonne numérique
clean_numeric = lambda s: pd.to_numeric(
    s.astype(str)
     .str.replace('\u202f', '', regex=False)
     .str.replace('\xa0',   '', regex=False)
     .str.replace(' ',      '', regex=False)
     .str.strip(),
    errors='coerce'
)

for col in cols_numeriques:
    if col in df.columns:
        df[col] = clean_numeric(df[col])

assert df.isnull().sum().sum() == 0, 'Valeurs manquantes détectées !'
print('[3/4] Nettoyage OK — 0 valeur manquante')

# -- Construction table silver --------------------------------------------
df_silver = df[['Code arrondissement', 'Nom arrondissement',
                'Logements', 'Établissements',
                'Meilleure estimation des locaux T4 2025',
                'T4 2025']].copy()

df_silver.columns = ['code_arrondissement', 'nom_arrondissement',
                     'nb_logements', 'nb_etablissements',
                     'locaux_total', 'locaux_fibres_T4_2025']

# Vectorisé au lieu de apply(lambda)
df_silver['code_postal'] = df_silver['code_arrondissement'] - 75100 + 75000

df_silver = df_silver.sort_values('code_arrondissement').reset_index(drop=True)
print(f'[4/4] Table silver construite — shape : {df_silver.shape}')

# -- Export Parquet -------------------------------------------------------
parquet_path = os.path.join(SILVER_DIR, 'fibre_paris_silver.parquet')
df_silver.to_parquet(parquet_path, index=False)
print(f'✓ Parquet créé : {parquet_path}')

print('\n=== SILVER fibre OK ===')
print(df_silver.to_string(index=False))