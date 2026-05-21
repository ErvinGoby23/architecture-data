"""
silver_stationnement.py
Nettoyage + jointure spatiale stationnement → arrondissement + code postal
"""

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement des données...")
df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/stationnement-voie-publique-emplacements.csv', sep=';', low_memory=False)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')
print(f"   Arrondissements chargés : {df_arr.shape}")

# ── 2. Suppression colonnes inutiles ──────────────────────────────────────
print("\n🗑️  Suppression colonnes quasi-vides...")
cols_drop = [
    'Compétence préfecture',    # 100% vide
    'Numéro IRIS',              # 100% vide
    'Numéro ilot',              # 100% vide
    'Plage horaire 1-Début',    # 99% vide
    'Plage horaire 1-Fin',      # 99% vide
    'Plage horaire 2-Début',    # 99% vide
    'Plage horaire 2-Fin',      # 99% vide
    'Plage horaire 3-Début',    # 99% vide
    'Plage horaire 3-Fin',      # 99% vide
    'Complément numéro voie',   # 90% vide
    'Nouvel identifiant',       # 65% vide
    'Ancien identifiant',       # 35% vide
    'Numéro mobilier',          # inutile
    'Type mobilier',            # 57% vide
    'Numéro séquentiel Tronçon voie',
    '1er numéro tronçon voie',
    'Dernier numéro tronçon voie',
]
cols_drop = [c for c in cols_drop if c in df.columns]
df = df.drop(columns=cols_drop)
print(f"   {len(cols_drop)} colonnes supprimées")
print(f"   Colonnes restantes : {len(df.columns)}")

# ── 3. Nettoyage de base ──────────────────────────────────────────────────
print("\n🧹 Nettoyage...")

# Filtrer arrondissements valides 1–20
before = len(df)
df = df[df['Arrondissement'].between(1, 20)]
print(f"   Arrond. aberrants supprimés : {before - len(df)}")

# Doublons
before = len(df)
df = df.drop_duplicates()
print(f"   Doublons supprimés          : {before - len(df)}")
print(f"   Shape après nettoyage       : {df.shape}")

# ── 4. Renommage snake_case ───────────────────────────────────────────────
print("\n✏️  Renommage colonnes...")
df = df.rename(columns={
    'Régime prioritaire'        : 'regime_prioritaire',
    'Régime particulier'        : 'regime_particulier',
    'Type de stationnement'     : 'type_stationnement',
    'Arrondissement'            : 'arrondissement_source',
    'Nombre places calculées'   : 'nb_places_calcules',
    'Nombre places réelles'     : 'nb_places_reelles',
    'Zones Résidentielles'      : 'zone_residentielle',
    'Localisation stationnement': 'localisation',
    'Numéro voie'               : 'numero_voie',
    'Type voie'                 : 'type_voie',
    'Nom voie'                  : 'nom_voie',
    'Localisation numéro'       : 'localisation_numero',
    'Parité'                    : 'parite',
    'Longueur'                  : 'longueur',
    'Largeur'                   : 'largeur',
    'Surface calculée'          : 'surface_calculee',
    'Signalisation horizontale' : 'signalisation_h',
    'Signalisation verticale'   : 'signalisation_v',
    'Conformité signalisation'  : 'conformite_signal',
    'Code voie Ville de Paris'  : 'code_voie',
    'Zone ASP'                  : 'zone_asp',
    'Numéro Section Territoriale de Voirie': 'section_voirie',
    'Dernière modification'     : 'date_modif',
    'Date du relevé'            : 'date_releve',
})

# Typage dates
df['date_modif']  = pd.to_datetime(df.get('date_modif'),  errors='coerce')
df['date_releve'] = pd.to_datetime(df.get('date_releve'), errors='coerce')

# ── 5. Conversion geo_shape → géométrie ───────────────────────────────────
print("\n📍 Parsing géométrie...")
def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

df['geometry'] = df['geo_shape'].apply(parse_geometry)
before = len(df)
df = df.dropna(subset=['geometry'])
print(f"   Géométries invalides supprimées : {before - len(df)}")

gdf_stat = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
gdf_stat = gdf_stat.drop(columns=['geo_shape', 'geo_point_2d'], errors='ignore')

# ── 6. Polygones arrondissements ──────────────────────────────────────────
print("🗺️  Chargement polygones arrondissements...")

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)

col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

print(f"   Géométrie  : {geo_col_arr}")
print(f"   Num arrond : {col_num}")
print(f"   INSEE      : {col_insee}")

df_arr['geometry'] = df_arr[geo_col_arr].apply(lambda x: shape(json.loads(x)))
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# ── 7. Jointure spatiale ──────────────────────────────────────────────────
print("\n🔗 Jointure spatiale en cours...")
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_stat, gdf_arr[cols_arr], how='left', predicate='within')
print(f"   Shape après jointure : {resultat.shape}")

# ── 8. Code postal + arrondissement ──────────────────────────────────────
if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = resultat['arrondissement'].apply(
        lambda x: 75000 + x if x > 0 else None
    )
if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

# ── 9. Filtrage Paris + nettoyage final ───────────────────────────────────
df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"\n   Emplacements Paris retenus : {len(df_final):,}")
print(f"   Arrondissements            : {sorted(df_final['arrondissement'].unique())}")

cols_drop_final = ['code_insee', 'arrondissement_insee', 'arrondissement', 'arrondissement_source', 'code_insee_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

# ── 10. Sauvegarde ────────────────────────────────────────────────────────
os.makedirs('silver', exist_ok=True)
output = 'nettoyage-indicateur1/stationnement_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale  : {df_final.shape}")

# ── 11. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucun emplacement trouvé — vérifier la jointure spatiale")
else:
    # Parser lat/lon depuis geo_point_2d si dispo, sinon depuis geometry centroid
    echantillons = df_final.sample(n=min(5, len(df_final)), random_state=42)
    for _, row in echantillons.iterrows():
        nom_voie = row.get('nom_voie', 'N/A')
        cp       = int(row['code_postal'])
        arrond   = int(row['arrondissement'])
        # Récupérer lat/lon depuis geo_point_2d original
        try:
            lat, lon = map(float, str(row.get('geo_point_2d', '')).split(','))
        except Exception:
            lat, lon = 0, 0
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        print(f"\nVoie    : {nom_voie}")
        print(f"Arrond. : {arrond}")
        print(f"CP      : {cp}")
        print(f"Lien    : {maps_url}")

print("\n--- FIN ---")
