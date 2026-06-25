"""
silver_espaces_verts.py — Nettoyage Espaces Verts Paris
Score de Vivabilité · Silver layer
"""

import pandas as pd
import os
import sys
import csv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
FILE        = os.path.join(BRUTE_DIR, 'espaces_verts.csv')

# ==========================================================================
# 1. LECTURE (champs GeoJSON volumineux → QUOTE_NONE)
# ==========================================================================
df = pd.read_csv(
    FILE,
    sep=';',
    engine='python',
    on_bad_lines='skip',
    quoting=csv.QUOTE_NONE,
    escapechar='\\',
)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")
print(f"Colonnes : {list(df.columns)}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
# Colonnes clés
df['ARRONDISSEMENT'] = pd.to_numeric(df['ARRONDISSEMENT'], errors='coerce').astype('Int64')

# Conversion 75001→1, 75020→20
df['ARRONDISSEMENT'] = df['ARRONDISSEMENT'].apply(
    lambda x: x - 75000 if pd.notna(x) and 75001 <= x <= 75020 else pd.NA
).astype('Int64')

# Extraction lat/lon depuis geo_point_2d ("lat, lon")
coords = df['geo_point_2d'].str.split(',', expand=True)
df['latitude']  = pd.to_numeric(coords[0], errors='coerce')
df['longitude'] = pd.to_numeric(coords[1], errors='coerce')

# Surface végétation (colonne numérique)
surf_col = next((c for c in df.columns if 'surface' in c.lower()), None)
if surf_col:
    df['surface_m2'] = pd.to_numeric(df[surf_col].astype(str).str.replace(',', '.'), errors='coerce')
    print(f"Surface extraite depuis : {surf_col}")

# Standardisation type espace vert
type_col = next((c for c in df.columns if 'type' in c.lower() and 'vert' in c.lower()), None)
if not type_col:
    type_col = next((c for c in df.columns if 'type' in c.lower()), None)

if type_col:
    df['type_espace_vert'] = df[type_col].str.strip().str.title()
    print(f"Type espace vert depuis : {type_col}")

# Filtrage Paris uniquement (arrondissements 1–20)
before = len(df)
df = df[df['ARRONDISSEMENT'].between(1, 20)].copy()
print(f"Hors Paris supprimés : {before - len(df)}")

before = len(df)
df = df.dropna(subset=['ARRONDISSEMENT'])
print(f"Sans arrondissement supprimés : {before - len(df)}")

# Colonnes finales
col_nom = next((c for c in df.columns if c.upper() == 'NOM'), None)
col_statut = next((c for c in df.columns if 'statut' in c.lower() or 'ouverture' in c.lower()), None)

cols_keep = ['ID', 'ARRONDISSEMENT', 'latitude', 'longitude']
if col_nom:       cols_keep.append(col_nom)
if type_col:      cols_keep.append('type_espace_vert')
if surf_col:      cols_keep.append('surface_m2')
if col_statut:    cols_keep.append(col_statut)

cols_keep = [c for c in cols_keep if c in df.columns]
df_clean = df[cols_keep].copy()

df_clean = df_clean.rename(columns={
    'ID'              : 'id_espace_vert',
    'ARRONDISSEMENT'  : 'arrondissement',
})
if col_nom:
    df_clean = df_clean.rename(columns={col_nom: 'nom'})

print(f"Shape après nettoyage : {df_clean.shape}")

# ==========================================================================
# 3. AGRÉGATION PAR ARRONDISSEMENT
# ==========================================================================
agg_base = df_clean.groupby('arrondissement').agg(
    nb_espaces_verts = ('id_espace_vert', 'count'),
).reset_index()

# Surface totale et moyenne
if 'surface_m2' in df_clean.columns:
    agg_surf = df_clean.groupby('arrondissement')['surface_m2'].agg(
        surface_totale_m2 = 'sum',
        surface_moy_m2    = 'mean',
        nb_grands_espaces = lambda x: (x > 10_000).sum(),  # > 1 ha
    ).reset_index()
    agg_base = agg_base.merge(agg_surf, on='arrondissement', how='left')

# Pivot par type d'espace
if 'type_espace_vert' in df_clean.columns:
    type_pivot = df_clean.groupby(['arrondissement', 'type_espace_vert']).size().unstack(fill_value=0)

    def clean_col(s):
        return (s.lower()
                 .replace(' ', '_').replace('-', '_')
                 .replace('é', 'e').replace('è', 'e').replace('ê', 'e')
                 .replace('à', 'a').replace('â', 'a')
                 .replace("'", '').replace('(', '').replace(')', ''))

    type_pivot.columns = [f'nb_{clean_col(c)}' for c in type_pivot.columns]
    type_pivot = type_pivot.reset_index()
    agg_base = agg_base.merge(type_pivot, on='arrondissement', how='left')

df_final = agg_base.sort_values('arrondissement').reset_index(drop=True)

print(f"\nShape agrégée (1 ligne / arrondissement) : {df_final.shape}")
print(df_final[['arrondissement', 'nb_espaces_verts'] +
               (['surface_totale_m2', 'nb_grands_espaces'] if 'surface_totale_m2' in df_final.columns else [])
              ].to_string(index=False))

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
output_dir = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(output_dir, exist_ok=True)

out_long = os.path.join(output_dir, 'espaces_verts_long_silver.parquet')
out_agg  = os.path.join(output_dir, 'espaces_verts_agrege_silver.parquet')

df_clean.to_parquet(out_long, index=False)
df_final.to_parquet(out_agg,  index=False)

print(f"\n✓ Parquet long    : {out_long}  ({len(df_clean):,} espaces)")
print(f"✓ Parquet agrégé  : {out_agg}  ({len(df_final)} arrondissements)")
print(f"Colonnes agrégé   : {list(df_final.columns)}")
