"""
silver_criminalite.py — Nettoyage Criminalité par commune (CODGEO)
Score de Vivabilité · Silver layer
Année de référence : 2024
"""

import pandas as pd
import os
from datetime import datetime
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilite')
FILE        = os.path.join(BRUTE_DIR, 'criminalite.csv')

ANNEE_REF = 2024

SILVER_BASE = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'indicateur3', 'nettoyage-indicateur3')

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

print(f"=== SILVER CRIMINALITE — Année : {ANNEE_REF} ===")

# ==========================================================================
# 1. LECTURE en chunks + filtre Paris + filtre 2024
# ==========================================================================
print("Lecture criminalite.csv (592 Mo) en chunks...")
chunks = []
for chunk in pd.read_csv(FILE, sep=';', engine='python', chunksize=100_000,
                          quotechar='"', dtype=str):
    chunk.columns = chunk.columns.str.strip().str.replace('\ufeff', '', regex=False)
    chunk = chunk[chunk['CODGEO_2025'].astype(str).str.startswith('75')]
    chunk = chunk[chunk['annee'].astype(str).str.strip() == str(ANNEE_REF)]
    chunks.append(chunk)

df = pd.concat(chunks, ignore_index=True)
print(f"Shape après filtre Paris + {ANNEE_REF} : {df.shape}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
df['annee']     = pd.to_numeric(df['annee'],     errors='coerce').astype('Int64')
df['nombre']    = pd.to_numeric(df['nombre'],     errors='coerce')
df['insee_pop'] = pd.to_numeric(df['insee_pop'], errors='coerce')
df['taux_pour_mille'] = (
    df['taux_pour_mille']
    .astype(str).str.replace(',', '.')
    .pipe(pd.to_numeric, errors='coerce')
)

df['arrondissement'] = df['CODGEO_2025'].astype(str).str[-2:].astype(int)
print(f"Arrondissements Paris : {sorted(df['arrondissement'].unique())}")

before = len(df)
df = df[df['est_diffuse'] == 'diff'].copy()
print(f"Non diffusées supprimées : {before - len(df)}")

cols_drop = ['complement_info_nombre', 'complement_info_taux',
             'insee_pop_millesime', 'insee_log_millesime', 'CODGEO_2025']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

print(f"Indicateurs distincts : {df['indicateur'].nunique()}")

# ==========================================================================
# 3. PIVOT : 1 ligne par arrondissement
# ==========================================================================
def clean_col(s):
    return (s.lower()
             .replace(' ', '_').replace("'", '').replace('/', '_')
             .replace('-', '_').replace('é', 'e').replace('è', 'e')
             .replace('ê', 'e').replace('à', 'a').replace('â', 'a'))

agg = df.groupby(['arrondissement', 'indicateur']).agg(
    nb_faits      = ('nombre',          'sum'),
    taux_moy      = ('taux_pour_mille', 'mean'),
    pop_reference = ('insee_pop',       'first'),
).reset_index()

pivot_taux = agg.pivot_table(index='arrondissement', columns='indicateur', values='taux_moy', aggfunc='mean', fill_value=0)
pivot_taux.columns = [f'taux_{clean_col(c)}' for c in pivot_taux.columns]

pop = df.groupby('arrondissement')['insee_pop'].first().reset_index()
df_final = pop.merge(pivot_taux.reset_index(), on='arrondissement', how='left')
df_final['annee'] = ANNEE_REF
df_final = df_final.sort_values('arrondissement').reset_index(drop=True)

print(f"\nShape finale : {df_final.shape}")
print(f"Arrondissements couverts : {df_final['arrondissement'].nunique()}")

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
output_dir = os.path.join(SILVER_BASE, date_str)
os.makedirs(output_dir, exist_ok=True)

out = os.path.join(output_dir, 'criminalite_silver.parquet')
df_final.to_parquet(out, index=False)

print(f"\n✓ Parquet : {out}  ({len(df_final)} lignes)")
print(f"Colonnes  : {list(df_final.columns)}")
