"""
transform_antennes_silver.py — Pipeline Silver · Indicateur 2 : Antennes relais
Urban Data Explorer
"""

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime

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

#  Extraction coords vectorisée 
geo = df['geo_point_2d'].tolist()
df['latitude']  = pd.to_numeric([x.get('lat') if isinstance(x, dict) else None for x in geo], errors='coerce')
df['longitude'] = pd.to_numeric([x.get('lon') if isinstance(x, dict) else None for x in geo], errors='coerce')

# Suppression colonnes inutiles
cols_drop = [
    'geo_point_2d', 'geo_shape', 'mise_en_serv_5g_700', 'se_anno_cad_data',
    'adresse', 'mise_en_serv', 'mise_en_serv_4g', 'mise_en_serv_5g_3500'
]
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

# Nettoyage vectorisé
df['operateur'] = df['operateur'].str.upper().str.strip()
df['type']      = df['type'].fillna('NON RENSEIGNÉ')


#  Génération dominante (hiérarchie 5G > 4G > 3G > 2G)
def generation(t):
    if pd.isna(t) or t == 'NON RENSEIGNÉ': return '2G'
    if '5G' in t: return '5G'
    if '4G' in t: return '4G'
    if '3G' in t: return '3G'
    return '2G'

df['generation'] = df['type'].apply(generation)
df['has_5g'] = df['generation'] == '5G'
df['has_4g'] = df['generation'] == '4G'
df['has_3g'] = df['generation'] == '3G'
df['has_2g'] = df['generation'] == '2G'

print(f"Antennes 5G : {df['has_5g'].sum()} ({df['has_5g'].mean()*100:.1f}%)")
print(f"Antennes 4G : {df['has_4g'].sum()} ({df['has_4g'].mean()*100:.1f}%)")
print(f"Antennes 3G : {df['has_3g'].sum()} ({df['has_3g'].mean()*100:.1f}%)")
print(f"Antennes 2G : {df['has_2g'].sum()} ({df['has_2g'].mean()*100:.1f}%)")
print(f"Total vérifié : {df[['has_5g','has_4g','has_3g','has_2g']].sum().sum()} == {len(df)}")
# Filtrage coords
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

# Spatial join sur les vraies frontières des arrondissements
df_arr    = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

def parse_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

gdf_antennes = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
    crs="EPSG:4326"
)

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_antennes, gdf_arr[cols_arr], how='inner', predicate='within')
print(f"Shape après jointure spatiale : {resultat.shape}")

if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

df_final = pd.DataFrame(resultat.drop(columns=[
    c for c in ['index_right', 'geometry', col_num, col_insee] if c in resultat.columns
]))

df_final = df_final[df_final['arrondissement'].between(1, 20)].copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)

print(f"Antennes Paris retenues : {len(df_final):,}")
print(f"Code postaux uniques : {sorted(df_final['code_postal'].unique())}")

# Suppression colonnes inutiles finales
cols_drop_final = ['ardt']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

# Validation spatiale 
print("\n=== VALIDATION SPATIALE (échantillon 5 points) ===")
sample = df_final.groupby('code_postal').first().reset_index()[
    ['code_postal', 'latitude', 'longitude', 'operateur']
].head(5)
for _, r in sample.iterrows():
    print(
        f"  CP {int(r['code_postal'])} | {r['operateur']}\n"
        f"  → https://www.google.com/maps?q={r['latitude']},{r['longitude']}"
    )

# Export Parquet
output_dir = os.path.join('nettoyage-indicateur2', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'antennes_relais_paris_silver.parquet')

df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")