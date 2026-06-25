"""
silver_criminalite.py — Nettoyage Criminalité par commune (CODGEO)
Score de Vivabilité · Silver layer
"""

import pandas as pd
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
FILE        = os.path.join(BRUTE_DIR, 'criminalite.csv')

# ==========================================================================
# 1. LECTURE (fichier 592 Mo — lecture par chunks)
# ==========================================================================
print("Lecture criminalite.csv (592 Mo) en chunks...")
chunks = []
for chunk in pd.read_csv(FILE, sep=';', engine='python', chunksize=100_000,
                          quotechar='"', dtype=str):
    chunk.columns = chunk.columns.str.strip().str.replace('\ufeff', '', regex=False)
    # Filtre immédiat sur Paris uniquement (CODGEO commence par 75)
    chunk = chunk[chunk['CODGEO_2025'].astype(str).str.startswith('75')]
    chunks.append(chunk)

df = pd.concat(chunks, ignore_index=True)
print(f"Shape après filtre Paris : {df.shape}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
# Conversion types
df['annee']       = pd.to_numeric(df['annee'],       errors='coerce').astype('Int64')
df['nombre']      = pd.to_numeric(df['nombre'],       errors='coerce')
df['insee_pop']   = pd.to_numeric(df['insee_pop'],   errors='coerce')
df['insee_log']   = pd.to_numeric(df['insee_log'],   errors='coerce')
df['taux_pour_mille'] = (
    df['taux_pour_mille']
    .astype(str)
    .str.replace(',', '.')
    .pipe(pd.to_numeric, errors='coerce')
)

# Arrondissement depuis CODGEO : 75101 → 1, 75120 → 20
df['arrondissement'] = df['CODGEO_2025'].astype(str).str[-2:].astype(int)
print(f"Arrondissements Paris : {sorted(df['arrondissement'].unique())}")

# Garder uniquement lignes diffusées
before = len(df)
df_diff = df[df['est_diffuse'] == 'diff'].copy()
print(f"Non diffusées supprimées : {before - len(df_diff)}")

# Supprimer colonnes inutiles pour Gold
cols_drop = ['complement_info_nombre', 'complement_info_taux',
             'insee_pop_millesime', 'insee_log_millesime', 'CODGEO_2025']
df_diff = df_diff.drop(columns=[c for c in cols_drop if c in df_diff.columns])

print(f"Indicateurs distincts : {df_diff['indicateur'].nunique()}")
print(df_diff['indicateur'].value_counts().to_string())

# ==========================================================================
# 3. PIVOT : 1 ligne par arrondissement, 1 colonne par indicateur
# ==========================================================================
# Agrégation par arrondissement + indicateur
agg = df_diff.groupby(['arrondissement', 'indicateur']).agg(
    nb_faits      = ('nombre',          'sum'),
    taux_moy      = ('taux_pour_mille', 'mean'),
    pop_reference = ('insee_pop',       'first'),
).reset_index()

# Pivot large : une colonne par indicateur
pivot_nb   = agg.pivot_table(index='arrondissement', columns='indicateur', values='nb_faits',   aggfunc='sum', fill_value=0)
pivot_taux = agg.pivot_table(index='arrondissement', columns='indicateur', values='taux_moy',   aggfunc='mean', fill_value=0)

def clean_col(s):
    return (s.lower()
             .replace(' ', '_')
             .replace("'", '')
             .replace('/', '_')
             .replace('-', '_')
             .replace('é', 'e').replace('è', 'e').replace('ê', 'e')
             .replace('à', 'a').replace('â', 'a'))

pivot_nb.columns   = [f'nb_{clean_col(c)}'   for c in pivot_nb.columns]
pivot_taux.columns = [f'taux_{clean_col(c)}' for c in pivot_taux.columns]

pop = df_diff.groupby('arrondissement')['insee_pop'].first().reset_index()

df_final = pop.merge(pivot_nb.reset_index(),   on='arrondissement', how='left')
df_final = df_final.merge(pivot_taux.reset_index(), on='arrondissement', how='left')
df_final = df_final.sort_values('arrondissement').reset_index(drop=True)

print(f"\nShape finale (1 ligne / arrondissement) : {df_final.shape}")
print(f"Arrondissements couverts : {df_final['arrondissement'].nunique()}")

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
output_dir = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(output_dir, exist_ok=True)

out_long  = os.path.join(output_dir, 'criminalite_long_silver.parquet')
out_pivot = os.path.join(output_dir, 'criminalite_pivot_silver.parquet')

df_diff.to_parquet(out_long,  index=False)
df_final.to_parquet(out_pivot, index=False)

print(f"\n✓ Parquet long  : {out_long}")
print(f"✓ Parquet pivot : {out_pivot}")
print(f"Colonnes pivot  : {list(df_final.columns)}")
