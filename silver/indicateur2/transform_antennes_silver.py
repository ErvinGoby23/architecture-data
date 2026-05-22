"""
silver_antennes.py — Pipeline Silver · Indicateur 2 : Score de connectivité (Pilier Mobile)
Urban Data Explorer

Source  : brute/Score de connectivité/antennes-relais.csv
Output  : silver/Score de connectivité/antennes_paris_silver.csv

Table silver produite :
    code_arrondissement     int     ex: 75101
    code_postal             int     ex: 75001
    nb_antennes             int     total antennes par arrondissement
    nb_antennes_4g          int     antennes avec 4G active
    nb_antennes_5g          int     antennes avec 5G - 3500 active
    operateur_leader        str     opérateur le plus présent

Usage :
    python silver_antennes.py
"""

import pandas as pd
import os

# ── Chemins ────────────────────────────────────────────────────────────────
BRONZE_FILE = '../../brute/Score de connectivité/antennes-relais.csv'
SILVER_DIR  = '../../silver/Score de connectivité/'

os.makedirs(SILVER_DIR, exist_ok=True)

# ── 1. Chargement ──────────────────────────────────────────────────────────
df = pd.read_csv(BRONZE_FILE, sep=None, engine='python', encoding='utf-8')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f'[1/5] Chargement OK — shape brut : {df.shape}')

# ── 2. Nettoyage colonnes inutiles & ligne parasite ────────────────────────
df = df.drop(columns=['Mise en service 5G - 700', 'se_anno_cad_data', 'geo_shape'])
df = df[df['Arrondissement'] != 76007].copy()
print(f'[2/5] Nettoyage OK — shape après drop : {df.shape}')

# ── 3. Harmonisation arrondissements (75001-75020 → 75101-75120) ───────────
def normalize_arrondissement(code):
    if 75001 <= code <= 75020:
        return code + 100
    return code

df['code_arrondissement'] = df['Arrondissement'].apply(normalize_arrondissement)
df = df[df['code_arrondissement'].between(75101, 75120)].copy()

# Normalisation opérateur
df['Opérateur'] = df['Opérateur'].str.upper().str.strip()
print(f'[3/5] Harmonisation OK — {df["code_arrondissement"].nunique()} arrondissements')

# ── 4. Agrégation par arrondissement ───────────────────────────────────────
def count_not_null(x):
    return x.notna().sum()

def operateur_dominant(x):
    return x.value_counts().idxmax()

df_silver = df.groupby('code_arrondissement').agg(
    nb_antennes      = ('Code site',                 'count'),
    nb_antennes_4g   = ('Mise en service 4G',        count_not_null),
    nb_antennes_5g   = ('Mise en service 5G - 3500', count_not_null),
    operateur_leader = ('Opérateur',                 operateur_dominant)
).reset_index()

# Code postal (donnée administrative directe)
df_silver['code_postal'] = df_silver['code_arrondissement'] - 75100 + 75000

df_silver = df_silver.sort_values('code_arrondissement').reset_index(drop=True)
print(f'[4/5] Agrégation OK — shape silver : {df_silver.shape}')

# ── 5. Export CSV ──────────────────────────────────────────────────────────
csv_path = SILVER_DIR + 'antennes_paris_silver.csv'
df_silver.to_csv(csv_path, index=False, encoding='utf-8-sig')
print(f'[5/5] ✓ CSV : {csv_path}')

print('\n=== SILVER antennes OK ===')
print(df_silver.to_string(index=False))