"""
silver_espaces_verts.py — Nettoyage Espaces Verts Paris
Score de Vivabilité · Silver layer
Snapshot 2024 (source unique)
"""

import pandas as pd
import geopandas as gpd
import json
import os
import sys
import csv
from shapely.geometry import shape
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilite')
FILE        = os.path.join(BRUTE_DIR, 'espaces_verts.csv')

SILVER_BASE = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'indicateur3', 'nettoyage-indicateur3')

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
print(f"=== SILVER ESPACES VERTS — Date : {date_str} ===")

# ==========================================================================
# 1. LECTURE
# ==========================================================================
df = pd.read_csv(FILE, sep=';', engine='python', on_bad_lines='skip',
                 quoting=csv.QUOTE_NONE, escapechar='\\')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
df['ARRONDISSEMENT'] = pd.to_numeric(df['ARRONDISSEMENT'], errors='coerce').astype('Int64')
df['ARRONDISSEMENT'] = df['ARRONDISSEMENT'].apply(
    lambda x: x - 75000 if pd.notna(x) and 75001 <= x <= 75020 else pd.NA
).astype('Int64')

coords = df['geo_point_2d'].str.split(',', expand=True)
df['latitude']  = pd.to_numeric(coords[0], errors='coerce')
df['longitude'] = pd.to_numeric(coords[1], errors='coerce')

surf_col = next((c for c in df.columns if 'surface' in c.lower()), None)
if surf_col:
    df['surface_m2'] = pd.to_numeric(df[surf_col].astype(str).str.replace(',', '.'), errors='coerce')
    print(f"Surface extraite depuis : {surf_col}")

type_col = next((c for c in df.columns if 'type' in c.lower() and 'vert' in c.lower()), None)
if type_col:
    df['type_espace_vert'] = df[type_col].str.strip().str.title()

before = len(df)
df = df[df['ARRONDISSEMENT'].between(1, 20)].dropna(subset=['ARRONDISSEMENT']).copy()
print(f"Hors Paris supprimés : {before - len(df)}")

col_nom = next((c for c in df.columns if c.upper() == 'NOM'), None)
cols_keep = ['ID', 'ARRONDISSEMENT', 'latitude', 'longitude']
if col_nom:  cols_keep.append(col_nom)
if type_col: cols_keep.append('type_espace_vert')
if surf_col: cols_keep.append('surface_m2')

df_clean = df[[c for c in cols_keep if c in df.columns]].copy().rename(columns={
    'ID': 'id_espace_vert', 'ARRONDISSEMENT': 'arrondissement',
})
if col_nom:
    df_clean = df_clean.rename(columns={col_nom: 'nom'})
df_clean['annee'] = 2024
print(f"Shape après nettoyage : {df_clean.shape}")

# ==========================================================================
# 3. JOINTURE QUARTIER
# ==========================================================================
def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

df_qu = pd.read_csv(
    os.path.join(ROOT_DIR, 'architecture-data', 'brute',
                 'indicateur-Score-accessibilité-mobilité', 'quartiers.csv'), sep=';'
)
df_qu.columns = df_qu.columns.str.strip()
geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_geometry)
gdf_qu = gpd.GeoDataFrame(df_qu.dropna(subset=['geometry']), geometry='geometry', crs="EPSG:4326")

df_coords = df_clean.dropna(subset=['latitude', 'longitude']).copy()
gdf_ev = gpd.GeoDataFrame(
    df_coords,
    geometry=gpd.points_from_xy(df_coords['longitude'], df_coords['latitude']),
    crs="EPSG:4326"
)

cols_qu_sel = [c for c in ['C_QU', 'L_QU', 'geometry'] if c in gdf_qu.columns]
res = gpd.sjoin(gdf_ev, gdf_qu[cols_qu_sel], how='left', predicate='within')
res = res.rename(columns={'C_QU': 'code_quartier', 'L_QU': 'nom_quartier'})

df_clean['code_quartier'] = None
df_clean['nom_quartier']  = None
idx = res.index[res['code_quartier'].notna()]
df_clean.loc[idx, 'code_quartier'] = res.loc[idx, 'code_quartier'].astype('Int64').values
df_clean.loc[idx, 'nom_quartier']  = res.loc[idx, 'nom_quartier'].values
print(f"Espaces verts avec code_quartier : {df_clean['code_quartier'].notna().sum()} / {len(df_clean)}")

# ==========================================================================
# 4. AGRÉGATION ARRONDISSEMENT
# ==========================================================================
def clean_col(s):
    return (s.lower().replace(' ', '_').replace('-', '_')
             .replace('é', 'e').replace('è', 'e').replace('ê', 'e')
             .replace('à', 'a').replace('â', 'a').replace("'", '')
             .replace('(', '').replace(')', ''))

agg_arr = df_clean.groupby('arrondissement').agg(
    nb_espaces_verts=('id_espace_vert', 'count'),
).reset_index()

if 'surface_m2' in df_clean.columns:
    agg_surf = df_clean.groupby('arrondissement')['surface_m2'].agg(
        surface_totale_m2='sum',
        surface_moy_m2='mean',
        nb_grands_espaces=lambda x: (x > 10_000).sum(),
    ).reset_index()
    agg_arr = agg_arr.merge(agg_surf, on='arrondissement', how='left')

if 'type_espace_vert' in df_clean.columns:
    type_pivot = df_clean.groupby(['arrondissement', 'type_espace_vert']).size().unstack(fill_value=0)
    type_pivot.columns = [f'nb_{clean_col(c)}' for c in type_pivot.columns]
    agg_arr = agg_arr.merge(type_pivot.reset_index(), on='arrondissement', how='left')

agg_arr['annee'] = 2024
df_final_arr = agg_arr.sort_values('arrondissement').reset_index(drop=True)
print(f"\nShape agrégée arrondissement : {df_final_arr.shape}")

# ==========================================================================
# 5. AGRÉGATION QUARTIER
# ==========================================================================
df_qu_valid = df_clean[df_clean['code_quartier'].notna()].copy()
df_qu_valid['code_quartier'] = df_qu_valid['code_quartier'].astype(int)

agg_qu = df_qu_valid.groupby('code_quartier').agg(
    nom_quartier     = ('nom_quartier',   'first'),
    arrondissement   = ('arrondissement', 'first'),
    nb_espaces_verts = ('id_espace_vert', 'count'),
).reset_index()

if 'surface_m2' in df_qu_valid.columns:
    agg_surf_qu = df_qu_valid.groupby('code_quartier')['surface_m2'].agg(
        surface_totale_m2='sum',
        surface_moy_m2='mean',
        nb_grands_espaces=lambda x: (x > 10_000).sum(),
    ).reset_index()
    agg_qu = agg_qu.merge(agg_surf_qu, on='code_quartier', how='left')

agg_qu['annee'] = 2024
df_final_qu = agg_qu.sort_values('code_quartier').reset_index(drop=True)
print(f"Shape agrégée quartier : {df_final_qu.shape}")

# ==========================================================================
# 6. EXPORT PARQUET versionné
#    - espaces_verts_long_silver.parquet  : points avec coords (pour MongoDB fusion)
#    - espaces_verts_silver.parquet       : agrégé arrondissement
#    - espaces_verts_quartier_silver.parquet : agrégé quartier
# ==========================================================================
output_dir = os.path.join(SILVER_BASE, date_str)
os.makedirs(output_dir, exist_ok=True)

out_long = os.path.join(output_dir, 'espaces_verts_long_silver.parquet')
out_arr  = os.path.join(output_dir, 'espaces_verts_silver.parquet')
out_qu   = os.path.join(output_dir, 'espaces_verts_quartier_silver.parquet')

df_clean.to_parquet(out_long, index=False)
df_final_arr.to_parquet(out_arr, index=False)
df_final_qu.to_parquet(out_qu,  index=False)

print(f"\n Parquet long            : {out_long}  ({len(df_clean):,} espaces)")
print(f" Parquet arrondissement  : {out_arr}  ({len(df_final_arr)} arrondissements)")
print(f" Parquet quartier        : {out_qu}  ({len(df_final_qu)} quartiers)")
print(f"Colonnes arrondissement  : {list(df_final_arr.columns)}")