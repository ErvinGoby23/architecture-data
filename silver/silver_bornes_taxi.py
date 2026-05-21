"""
silver_bornes_taxi.py
Nettoyage + jointure spatiale bornes taxi → arrondissement + code postal
"""

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape, Point
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement des données...")
df = pd.read_csv('../brute/indicateur-Score-accessibilité-mobilité/bornes-dappel-taxi.csv', sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Shape brute : {df.shape}")

df_arr = pd.read_csv('../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')
print(f"   Arrondissements chargés : {df_arr.shape}")

# ── 2. Parser geopoint → lat / lon ────────────────────────────────────────
print("\n📍 Parsing coordonnées...")
geo_col = next((c for c in df.columns if 'geopoint' in c.lower()), None)
print(f"   Colonne géo détectée : {geo_col}")

coords = df[geo_col].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0], errors='coerce')
df['lon'] = pd.to_numeric(coords[1], errors='coerce')

# ── 3. Nettoyage ──────────────────────────────────────────────────────────
print("\n🧹 Nettoyage...")
cols_drop = ['no_appel', 'info', 'geo_shape', 'geopoint', 'geopoint_datagouv']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   Sans coords supprimés  : {before - len(df)}")

before = len(df)
df = df[df['lat'].between(41, 51) & df['lon'].between(-5, 10)]
print(f"   Coords aberrantes      : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['id'])
print(f"   Doublons supprimés     : {before - len(df)}")
print(f"   Shape après nettoyage  : {df.shape}")

# ── 4. GeoDataFrame points ────────────────────────────────────────────────
print("\n📍 Création des points géographiques...")
df['geometry'] = df.apply(lambda row: Point(row['lon'], row['lat']), axis=1)
gdf_bornes = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

# ── 5. Polygones arrondissements ──────────────────────────────────────────
print("🗺️  Chargement polygones arrondissements...")

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)

col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

print(f"   Géométrie  : {geo_col_arr}")
print(f"   Num arrond : {col_num}")
print(f"   INSEE      : {col_insee}")

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# ── 6. Jointure spatiale ──────────────────────────────────────────────────
print("\n🔗 Jointure spatiale en cours...")
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_bornes, gdf_arr[cols_arr], how='left', predicate='within')
print(f"   Shape après jointure : {resultat.shape}")

# ── 7. Code postal + arrondissement ──────────────────────────────────────
if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = resultat['arrondissement'].apply(
        lambda x: 75000 + x if x > 0 else None
    )
if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

# ── 8. Filtrage Paris + nettoyage ─────────────────────────────────────────
df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"\n   Bornes Paris retenues : {len(df_final):,}")
print(f"   Arrondissements       : {sorted(df_final['arrondissement'].unique())}")

# ── 9. Renommage final ────────────────────────────────────────────────────
df_final = df_final.rename(columns={
    'id'          : 'borne_id',
    'nom'         : 'borne_nom',
    'emplacements': 'nb_emplacements',
    'statut'      : 'statut',
    'insee'       : 'code_insee_source',
})

# ── 10. Sauvegarde ────────────────────────────────────────────────────────
os.makedirs('silver', exist_ok=True)
output = 'silver/bornes_taxi_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale  : {df_final.shape}")

# ── 11. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucune borne trouvée — vérifier la jointure spatiale")
else:
    for _, row in df_final.sample(n=min(5, len(df_final)), random_state=42).iterrows():
        maps_url = f"https://www.google.com/maps?q={row['lat']},{row['lon']}"
        print(f"\nBorne   : {row.get('borne_nom', 'N/A')}")
        print(f"Adresse : {row.get('adresse', 'N/A')}")
        print(f"Arrond. : {int(row['arrondissement'])}")
        print(f"CP      : {int(row['code_postal'])}")
        print(f"Lien    : {maps_url}")

print("\n--- FIN ---")
