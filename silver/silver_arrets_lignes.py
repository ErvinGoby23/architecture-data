"""
silver_arrets_lignes.py
Nettoyage + jointure spatiale arrêts IDFM → arrondissement + code postal
"""

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape, Point
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement des données...")
df = pd.read_csv('../brute/indicateur-Score-accessibilité-mobilité/arrets-lignes.csv', sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Shape brute : {df.shape}")

df_arr = pd.read_csv('../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')
print(f"   Arrondissements chargés : {df_arr.shape}")
print(f"   Colonnes arrondissements : {list(df_arr.columns)}")

# ── 2. Renommage colonnes ─────────────────────────────────────────────────
df = df.rename(columns={
    'shortname'      : 'route_short_name',
    'mode'           : 'route_type',
    'nom_commune'    : 'commune',
    'operatorname'   : 'operateur',
    'route_long_name': 'ligne_nom',
    'code_insee'     : 'code_insee',
})

# ── 3. Nettoyage de base ──────────────────────────────────────────────────
print("\n🧹 Nettoyage...")
df = df.drop(columns=[c for c in ['bookingrules', 'pointgeo'] if c in df.columns])

df['stop_lat'] = pd.to_numeric(df['stop_lat'], errors='coerce')
df['stop_lon'] = pd.to_numeric(df['stop_lon'], errors='coerce')

before = len(df)
df = df.dropna(subset=['stop_lat', 'stop_lon'])
print(f"   Sans coords supprimés  : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['stop_id', 'route_short_name'])
print(f"   Doublons supprimés (stop_id + ligne) : {before - len(df)}")

# Filtrage IDF
df = df[
    df['stop_lat'].between(48.0, 49.4) &
    df['stop_lon'].between(1.4, 3.6)
].copy()
print(f"   Shape après filtrage IDF : {df.shape}")

# ── 4. GeoDataFrame points ────────────────────────────────────────────────
print("\n📍 Création des points géographiques...")
df['geometry'] = df.apply(lambda row: Point(row['stop_lon'], row['stop_lat']), axis=1)
gdf_arrets = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

# ── 5. Polygones arrondissements ──────────────────────────────────────────
print("🗺️  Chargement polygones arrondissements...")

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

# Prendre 'Geometry' exacte en priorité, pas 'Geometry X Y'
geo_col_arr  = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num      = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee    = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

print(f"   Géométrie  : {geo_col_arr}")
print(f"   Num arrond : {col_num}")
print(f"   INSEE      : {col_insee}")

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# ── 6. Jointure spatiale ──────────────────────────────────────────────────
print("\n🔗 Jointure spatiale en cours...")
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_arrets, gdf_arr[cols_arr], how='left', predicate='within')
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

print(f"\n   Arrêts Paris retenus  : {len(df_final):,}")
print(f"   Arrondissements       : {sorted(df_final['arrondissement'].unique())}")

# ── 9. Sauvegarde ─────────────────────────────────────────────────────────
os.makedirs('silver', exist_ok=True)
output = 'silver/arrets_lignes_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale  : {df_final.shape}")

# ── 10. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucun arrêt trouvé")
else:
  for _, row in df_final.sample(n=min(5, len(df_final)), random_state=42).iterrows():
    maps_url = f"https://www.google.com/maps?q={row['stop_lat']},{row['stop_lon']}"
    print(f"\nArrêt   : {row['stop_name']}")
    print(f"Arrond. : {int(row['arrondissement'])}")
    print(f"CP      : {int(row['code_postal'])}")
    print(f"Lien    : {maps_url}")

print("\n--- FIN ---")