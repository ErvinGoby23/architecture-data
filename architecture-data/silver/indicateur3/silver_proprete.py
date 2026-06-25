"""
silver_proprete.py — Nettoyage Propreté urbaine Paris (DansMaRue)
Score de Vivabilité · Silver layer
"""

import pandas as pd
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
FILE        = os.path.join(BRUTE_DIR, 'proprete.csv')

# Pondération par gravité du type de signalement (pour le score Gold)
POIDS_TYPE = {
    'Objets abandonnés'                                   : 3,
    'Autos, motos, vélos, trottinettes...'               : 3,
    'Graffitis, tags, affiches et autocollants'          : 2,
    'Dépôt sauvage de déchets'                           : 3,
    'Propreté'                                            : 1,
    'Mobilier urbain dégradé'                             : 2,
    'Nuisances liées aux animaux'                         : 1,
    'Voirie et espace public'                             : 2,
    'Eau'                                                 : 2,
    'Eclairage'                                           : 1,
}

# ==========================================================================
# 1. LECTURE (383 Mo — chunks)
# ==========================================================================
print("Lecture proprete.csv (383 Mo) en chunks...")
chunks = []
for chunk in pd.read_csv(FILE, sep=';', engine='python', chunksize=100_000,
                          dtype=str, on_bad_lines='skip'):
    chunk.columns = chunk.columns.str.strip().str.replace('\ufeff', '', regex=False)
    chunks.append(chunk)

df = pd.concat(chunks, ignore_index=True)
print(f"Shape brute : {df.shape}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
df['ARRONDISSEMENT']    = pd.to_numeric(df['ARRONDISSEMENT'],    errors='coerce').astype('Int64')
df['CODE POSTAL']       = pd.to_numeric(df['CODE POSTAL'],       errors='coerce').astype('Int64')
df['ANNEE DECLARATION'] = pd.to_numeric(df['ANNEE DECLARATION'], errors='coerce').astype('Int64')
df['MOIS DECLARATION']  = pd.to_numeric(df['MOIS DECLARATION'],  errors='coerce').astype('Int64')
df['DATE DECLARATION']  = pd.to_datetime(df['DATE DECLARATION'], errors='coerce')

# Correction CODE POSTAL aberrant (75248 → 75020)
df.loc[df['CODE POSTAL'] == 75248, 'CODE POSTAL'] = 75020
df.loc[df['CODE POSTAL'] == 75248, 'ARRONDISSEMENT'] = 20

# Filtrer Paris uniquement (arrondissements 1–20)
before = len(df)
df = df[df['ARRONDISSEMENT'].between(1, 20)].copy()
print(f"Hors Paris supprimés : {before - len(df)}")

before = len(df)
df = df.dropna(subset=['ARRONDISSEMENT', 'DATE DECLARATION'])
print(f"Lignes sans arrondissement/date supprimées : {before - len(df)}")

# Extraction lat/lon depuis geo_point_2d ("lat, lon")
coords = df['geo_point_2d'].str.split(',', expand=True)
df['latitude']  = pd.to_numeric(coords[0], errors='coerce')
df['longitude'] = pd.to_numeric(coords[1], errors='coerce')

# Poids signalement
df['poids'] = df['TYPE DECLARATION'].map(POIDS_TYPE).fillna(1).astype(int)

# Colonnes finales utiles
cols_keep = [
    'ID DECLARATION', 'TYPE DECLARATION', 'SOUS TYPE DECLARATION',
    'ARRONDISSEMENT', 'DATE DECLARATION', 'ANNEE DECLARATION', 'MOIS DECLARATION',
    'OUTIL SOURCE', 'latitude', 'longitude', 'poids',
]
df = df[[c for c in cols_keep if c in df.columns]].copy()

df = df.rename(columns={
    'ID DECLARATION'          : 'id_declaration',
    'TYPE DECLARATION'        : 'type_declaration',
    'SOUS TYPE DECLARATION'   : 'sous_type_declaration',
    'ARRONDISSEMENT'          : 'arrondissement',
    'DATE DECLARATION'        : 'date_declaration',
    'ANNEE DECLARATION'       : 'annee',
    'MOIS DECLARATION'        : 'mois',
    'OUTIL SOURCE'            : 'outil_source',
})

print(f"Shape après nettoyage : {df.shape}")
print(f"Arrondissements : {sorted(df['arrondissement'].dropna().unique().tolist())}")

# ==========================================================================
# 3. AGRÉGATION PAR ARRONDISSEMENT
# ==========================================================================
agg_arr = df.groupby('arrondissement').agg(
    nb_signalements      = ('id_declaration',      'count'),
    nb_types_distincts   = ('type_declaration',    'nunique'),
    score_poids_total    = ('poids',               'sum'),
    poids_moyen          = ('poids',               'mean'),
    annee_min            = ('annee',               'min'),
    annee_max            = ('annee',               'max'),
).reset_index()

# Pivot types
types_pivot = df.groupby(['arrondissement', 'type_declaration']).size().unstack(fill_value=0)

def clean_col(s):
    return (s.lower()
             .replace(' ', '_').replace(',', '').replace('.', '')
             .replace('é', 'e').replace('è', 'e').replace('ê', 'e')
             .replace('à', 'a').replace('â', 'a').replace('ô', 'o')
             .replace("'", '').replace('/', '_'))

types_pivot.columns = [f'nb_{clean_col(c)}' for c in types_pivot.columns]
types_pivot = types_pivot.reset_index()

df_final = agg_arr.merge(types_pivot, on='arrondissement', how='left')
df_final = df_final.sort_values('arrondissement').reset_index(drop=True)

print(f"\nShape agrégée (1 ligne / arrondissement) : {df_final.shape}")
print(df_final[['arrondissement', 'nb_signalements', 'score_poids_total']].to_string(index=False))

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
output_dir = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(output_dir, exist_ok=True)

out_long = os.path.join(output_dir, 'proprete_long_silver.parquet')
out_agg  = os.path.join(output_dir, 'proprete_agrege_silver.parquet')

df.to_parquet(out_long, index=False)
df_final.to_parquet(out_agg, index=False)

print(f"\n✓ Parquet long    : {out_long}  ({len(df):,} lignes)")
print(f"✓ Parquet agrégé  : {out_agg}  ({len(df_final)} arrondissements)")
print(f"Colonnes agrégé   : {list(df_final.columns)}")
