"""
transform_antennes_silver.py — Pipeline Silver · Indicateur 2 : Antennes relais
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER
"""

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BRONZE_BASE = os.path.join(CURRENT_DIR, '../../brute/Score-de-connectivite')

def get_latest_date(bronze_dir):
    dates = sorted([
        d for d in os.listdir(bronze_dir)
        if os.path.isdir(os.path.join(bronze_dir, d))
    ], reverse=True)
    if not dates:
        raise FileNotFoundError(f"Aucun dossier trouvé dans {bronze_dir}")
    return dates[0]

if len(sys.argv) > 1:
    date_str = sys.argv[1]
else:
    date_str = get_latest_date(BRONZE_BASE)

print(f"Date bronze utilisée : {date_str}")
path_antennes = os.path.join(BRONZE_BASE, date_str, 'antennes-relais.json')
print(f"📖 Lecture des données brutes du jour : {path_antennes}")

with open(path_antennes, encoding='utf-8') as f:
    data = json.load(f)

df = pd.DataFrame(data['records'])
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Extraction coordonnées
# Extraction coordonnées ultra rapide en C (Pandas natif)
coord_df = pd.json_normalize(df['geo_point_2d'])
df['latitude']  = pd.to_numeric(coord_df['lat'], errors='coerce')
df['longitude'] = pd.to_numeric(coord_df['lon'], errors='coerce')

cols_drop = ['geo_point_2d', 'geo_shape', 'mise_en_serv_5g_700', 'se_anno_cad_data',
             'adresse', 'mise_en_serv', 'mise_en_serv_4g', 'mise_en_serv_5g_3500']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

df['operateur'] = df['operateur'].str.upper().str.strip()
df['type']      = df['type'].fillna('NON RENSEIGNÉ')

df['generation'] = np.select(
    [
        df['type'].str.contains('5G', na=False),
        df['type'].str.contains('4G', na=False),
        df['type'].str.contains('3G', na=False),
    ],
    ['5G', '4G', '3G'],
    default='2G'
)
df['has_5g'] = df['generation'] == '5G'
df['has_4g'] = df['generation'] == '4G'
df['has_3g'] = df['generation'] == '3G'
df['has_2g'] = df['generation'] == '2G'

print(f"Antennes 5G : {df['has_5g'].sum()} ({df['has_5g'].mean()*100:.1f}%)")
print(f"Antennes 4G : {df['has_4g'].sum()} ({df['has_4g'].mean()*100:.1f}%)")
print(f"Antennes 3G : {df['has_3g'].sum()} ({df['has_3g'].mean()*100:.1f}%)")
print(f"Antennes 2G : {df['has_2g'].sum()} ({df['has_2g'].mean()*100:.1f}%)")
print(f"Total vérifié : {df[['has_5g','has_4g','has_3g','has_2g']].sum().sum()} == {len(df)}")

before = len(df)
df = df.dropna(subset=['latitude', 'longitude'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df[df['latitude'].between(48.7, 49.0) & df['longitude'].between(2.2, 2.5)].copy()
print(f"Hors bbox Paris supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['code_site'])
print(f"Doublons supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

# GeoDataFrame points antennes
gdf_antennes = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
    crs="EPSG:4326"
)

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None


# JOINTURE 1 — ARRONDISSEMENT (comme avant)

df_arr    = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')
geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat_arr = gpd.sjoin(gdf_antennes, gdf_arr[cols_arr], how='inner', predicate='within')
print(f"Shape après jointure arrondissement : {resultat_arr.shape}")

if col_num:
    resultat_arr['arrondissement'] = resultat_arr[col_num].fillna(0).astype(int)
    resultat_arr['code_postal']    = (resultat_arr['arrondissement'] + 75000).where(resultat_arr['arrondissement'] > 0)

df_final_arr = pd.DataFrame(resultat_arr.drop(columns=[
    c for c in ['index_right', 'geometry', col_num, col_insee] if c in resultat_arr.columns
]))
df_final_arr = df_final_arr[df_final_arr['arrondissement'].between(1, 20)].copy()
df_final_arr['code_postal'] = df_final_arr['code_postal'].astype(int)

print(f"Antennes Paris (arrondissement) retenues : {len(df_final_arr):,}")


# JOINTURE 2 — QUARTIER

df_qu = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/quartiers.csv', sep=';')
df_qu.columns = df_qu.columns.str.strip()

geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_geometry)
df_qu = df_qu.dropna(subset=['geometry'])
gdf_qu = gpd.GeoDataFrame(df_qu, geometry='geometry', crs="EPSG:4326")

cols_qu = ['C_QU', 'L_QU', 'C_AR', 'geometry']
cols_qu = [c for c in cols_qu if c in gdf_qu.columns]

resultat_qu = gpd.sjoin(gdf_antennes, gdf_qu[cols_qu], how='inner', predicate='within')
print(f"Shape après jointure quartier : {resultat_qu.shape}")

resultat_qu = resultat_qu.rename(columns={
    'C_QU': 'code_quartier',
    'L_QU': 'nom_quartier',
    'C_AR': 'arrondissement',
})

df_final_qu = pd.DataFrame(resultat_qu.drop(columns=[
    c for c in ['index_right', 'geometry'] if c in resultat_qu.columns
]))
df_final_qu['code_quartier']  = df_final_qu['code_quartier'].astype(int)
df_final_qu['arrondissement'] = df_final_qu['arrondissement'].astype(int)

print(f"Antennes Paris (quartier) retenues : {len(df_final_qu):,}")
print(f"Quartiers uniques : {df_final_qu['code_quartier'].nunique()}")


# VALIDATION SPATIALE

print("\n=== VALIDATION SPATIALE (échantillon 5 points) ===")
sample = df_final_arr.groupby('code_postal').first().reset_index()[
    ['code_postal', 'latitude', 'longitude', 'operateur']
].head(5)
for _, r in sample.iterrows():
    print(f"  CP {int(r['code_postal'])} | {r['operateur']}\n"
          f"  → https://www.google.com/maps?q={r['latitude']},{r['longitude']}")


# EXPORT PARQUET

output_dir = os.path.join('nettoyage-indicateur2', date_str)
os.makedirs(output_dir, exist_ok=True)

# Parquet arrondissement (identique à l'ancien)
output_arr = os.path.join(output_dir, 'antennes_relais_paris_silver.parquet')
df_final_arr.to_parquet(output_arr, index=False)
print(f"\n✓ Parquet arrondissement : {output_arr}")
print(f"Shape : {df_final_arr.shape}")

# Parquet quartier (nouveau)
output_qu = os.path.join(output_dir, 'antennes_relais_quartier_paris_silver.parquet')
df_final_qu.to_parquet(output_qu, index=False)
print(f"✓ Parquet quartier : {output_qu}")
print(f"Shape : {df_final_qu.shape}")
print(f"Colonnes : {list(df_final_qu.columns)}")