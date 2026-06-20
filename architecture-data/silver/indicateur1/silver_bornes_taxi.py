import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
# Lecture CSV brute 
df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/bornes-dappel-taxi.csv',
                 sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

# Extraction coords vectorisée 
geo_col   = next((c for c in df.columns if 'geopoint' in c.lower()), None)
coords    = df[geo_col].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0], errors='coerce')
df['lon'] = pd.to_numeric(coords[1], errors='coerce')

cols_drop = ['no_appel', 'info', 'geo_shape', 'geopoint', 'geopoint_datagouv']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df[df['lat'].between(41, 51) & df['lon'].between(-5, 10)]
print(f"Coords aberrantes : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['id'])
print(f"Doublons supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

# Géométrie vectorisée 
gdf_bornes = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['lon'], df['lat']),
    crs="EPSG:4326"
)

# Arrondissements
def parse_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_bornes, gdf_arr[cols_arr], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"Bornes Paris retenues : {len(df_final):,}")
print(f"Code postaux uniques : {sorted(df_final['code_postal'].unique())}")

df_final = df_final.rename(columns={
    'id'          : 'borne_id',
    'nom'         : 'borne_nom',
    'emplacements': 'nb_emplacements',
    'statut'      : 'statut',
    'insee'       : 'code_insee_source',
})

cols_drop_final = ['code_insee', 'arrondissement_insee', 'arrondissement', 'code_insee_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'bornes_taxi_paris_silver.parquet')
df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")