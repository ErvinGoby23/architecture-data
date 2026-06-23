import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime

# Date d'exécution pour le dossier de sortie
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

# 1. Lecture des fichiers bruts
df = pd.read_csv('../../brute/Score densité de services du quotidien/etablissements-scolaires-ecoles-elementaires.csv',
                 sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

# 2. Renommage des colonnes
df = df.rename(columns={
    'Libellé établissement'                 : 'etablissement_nom',
    'Adresse'                               : 'adresse',
    'Type établissement'                    : 'type_etablissement',
    'Année scolaire'                        : 'annee_scolaire',
    'Code INSEE'                            : 'code_insee',
    "Type d'établissement - Année scolaire" : 'libelle_source',
})

# 3. Extraction des coordonnées depuis geo_shape (GeoJSON Point)
def parse_point(val):
    try:
        g = json.loads(val)
        lon, lat = g['coordinates']
        return pd.Series({'lon': lon, 'lat': lat})
    except Exception:
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df['geo_shape'].apply(parse_point)
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

# Suppression des colonnes géographiques brutes inutiles
cols_drop = ['geo_shape', 'geo_point_2d', 'Arrondissement', 'canton_ville']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

# 4. Filtrage géographique (Île-de-France / Paris)
before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df[df['lat'].between(48.0, 49.4) & df['lon'].between(1.4, 3.6)].copy()
print(f"Hors IDF supprimés : {before - len(df)}")

# 5. 🔥 DÉDOUBLONNAGE AVEC CLÉ COMPOSITE (annee_scolaire + etablissement_nom)
# On ne supprime plus les anciennes années ! On s'assure juste qu'il n'y a pas 
# de doublon d'un même établissement au cours d'une MÊME année scolaire.
before = len(df)
df = df.sort_values('annee_scolaire', na_position='first')
df = df.drop_duplicates(subset=['annee_scolaire', 'etablissement_nom'], keep='last')
print(f"Doublons (au sein d'une même année) supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

# 6. Création du GeoDataFrame pour la jointure spatiale
gdf_ecoles = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['lon'], df['lat']),
    crs="EPSG:4326"
)

# 7. Préparation des arrondissements pour la jointure
def parse_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# Jointure spatiale
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_ecoles, gdf_arr[cols_arr], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

# 8. Calcul et enrichissement des codes postaux
if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

# Filet de sécurité code postal basé sur le Code INSEE (ex: 75101 -> 75001)
if 'code_insee' in resultat.columns:
    cp_insee = (resultat['code_insee'] - 75100 + 75000).where(
        resultat['code_insee'].between(75101, 75120))
    resultat['code_postal'] = resultat['code_postal'].fillna(cp_insee)

# Filtrage final pour ne garder que Paris (code postal valide)
df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)

# Nettoyage des colonnes techniques de géométrie et de jointure
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"Écoles Paris retenues (toutes années confondues) : {len(df_final):,}")
print(f"Codes postaux uniques : {sorted(df_final['code_postal'].unique())}")

# 9. Nettoyage des colonnes Silver (On préserve absolument 'annee_scolaire')
cols_drop_final = ['code_insee', 'arrondissement_insee', 'arrondissement', 'libelle_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

# 10. Exportation finale en Parquet
output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'ecoles_elementaires_paris_silver.parquet')

df_final.to_parquet(output, index=False)

print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes finales : {list(df_final.columns)}")