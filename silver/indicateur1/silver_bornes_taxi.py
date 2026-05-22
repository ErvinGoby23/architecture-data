import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape, Point
import os

df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/bornes-dappel-taxi.csv', sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

geo_col = next((c for c in df.columns if 'geopoint' in c.lower()), None)
coords = df[geo_col].str.split(',', expand=True)
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

def make_point(row):
    return Point(row['lon'], row['lat'])

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

def to_code_postal(arr):
    return 75000 + arr if arr > 0 else None

df['geometry'] = df.apply(make_point, axis=1)
gdf_bornes = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

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
    resultat['code_postal']    = resultat['arrondissement'].apply(to_code_postal)

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

os.makedirs('nettoyage-indicateur1', exist_ok=True)
output = 'nettoyage-indicateur1/bornes_taxi_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"Fichier créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")