import pandas as pd
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE
from datetime import datetime

# Ancrage des chemins sur l'emplacement du script (indépendant du répertoire courant)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.normpath(os.path.join(BASE_DIR, '..', '..', '..', '.env')))

# On suppose que l'on est sur l'Indicateur 4 (Services du quotidien)
GOLD_OUTPUT_DIR = os.path.join(BASE_DIR, 'indicateur_services')
os.makedirs(GOLD_OUTPUT_DIR, exist_ok=True)

print("=== EXÉCUTION DU SCRIPT DE FUSION (GOLD) : SERVICES DU QUOTIDIEN ===")

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver' # Ou 'gold' selon ton architecture

# ==========================================================================
# 1. LECTURE PARQUET (Sources Silver)
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")

# On récupère la date pour pointer vers le bon dossier
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

# Repli : si aucun dossier pour cette date, on prend le plus récent disponible
SILVER_BASE = os.path.join(BASE_DIR, 'nettoyage-indicateur1')
if not os.path.isdir(os.path.join(SILVER_BASE, date_str)) and os.path.isdir(SILVER_BASE):
    dispo = sorted([d for d in os.listdir(SILVER_BASE)
                    if os.path.isdir(os.path.join(SILVER_BASE, d))], reverse=True)
    if dispo:
        print(f"   ↳ Dossier {date_str} absent — bascule sur le plus récent : {dispo[0]}")
        date_str = dispo[0]

# On ajoute le {date_str} au chemin
PATH_ECOLES = os.path.join(BASE_DIR, 'nettoyage-indicateur1', date_str, 'ecoles_elementaires_paris_silver.parquet')

# Les autres chemins ne changent pas car on n'a pas mis de date
PATH_COMMIS = os.path.join(BASE_DIR, 'nettoyage-indicateur-commissariats', 'commissariats_paris_silver.parquet')
PATH_COMMER = os.path.join(BASE_DIR, 'nettoyage-indicateur-commerces', 'commerces_paris_silver.parquet')

df_ecoles = pd.read_parquet(PATH_ECOLES)
df_commis = pd.read_parquet(PATH_COMMIS)
df_commer = pd.read_parquet(PATH_COMMER)

print(f"Écoles        : {df_ecoles.shape}")
print(f"Commissariats : {df_commis.shape}")
print(f"Commerces     : {df_commer.shape}")

# ==========================================================================
# 2. PRÉPARATION ET AGRÉGATION (QUARTIER + ARRONDISSEMENT)
# ==========================================================================

# --- C. Commerces (arrondissement uniquement : source agrégée par commune) ---
# Conversion Code INSEE (751xx) -> Code Postal (750xx)
df_commer['code_postal'] = df_commer['code_insee'].astype(int) - 100
cols_to_sum = [c for c in df_commer.columns if c not in ['code_insee', 'code_postal', 'commune_nom', 'population_2010']]
df_commer['nb_commerces_total'] = df_commer[cols_to_sum].sum(axis=1)
agg_commer = df_commer[['code_postal', 'nb_commerces_total'] + cols_to_sum].copy()


def agreger_services(df_ecoles, df_commis, group_col):
    """Agrège écoles + commissariats sur group_col (code_quartier ou code_postal)."""
    # Écoles
    dfe = df_ecoles.dropna(subset=[group_col]).copy()
    agg_ecoles = dfe.groupby(group_col).agg(
        nb_ecoles=('etablissement_nom', 'nunique')
    ).reset_index()

    # Commissariats
    dfc = df_commis.dropna(subset=[group_col]).copy()
    agg_commis = dfc.groupby(group_col).agg(
        nb_commissariats=('commissariat_nom', 'nunique')
    ).reset_index()

    df = agg_ecoles.merge(agg_commis, on=group_col, how='outer')
    return df

# ==========================================================================
# 3. FUSION — NIVEAU ARRONDISSEMENT (écoles + commissariats + commerces)
# ==========================================================================
df_arr = agreger_services(df_ecoles, df_commis, 'code_postal')
df_arr = df_arr.merge(agg_commer, on='code_postal', how='outer')
df_arr = df_arr.fillna(0)
cols_int = [c for c in df_arr.columns if c != 'code_postal']
df_arr[cols_int] = df_arr[cols_int].astype(int)
df_arr['code_postal'] = df_arr['code_postal'].astype(int)
df_arr = df_arr.sort_values('code_postal').reset_index(drop=True)

# ==========================================================================
# 3 bis. FUSION — NIVEAU QUARTIER (écoles + commissariats, pas de commerces)
# ==========================================================================
df_quartier = agreger_services(df_ecoles, df_commis, 'code_quartier')
df_quartier = df_quartier.fillna(0)
cols_int_qu = [c for c in df_quartier.columns if c != 'code_quartier']
df_quartier[cols_int_qu] = df_quartier[cols_int_qu].astype(int)
df_quartier['code_quartier'] = df_quartier['code_quartier'].astype(int)

# Rattacher nom_quartier + code_postal (depuis les écoles, sinon commissariats)
src_noms = pd.concat([
    df_ecoles[['code_quartier', 'nom_quartier', 'code_postal']],
    df_commis[['code_quartier', 'nom_quartier', 'code_postal']],
], ignore_index=True).dropna(subset=['code_quartier'])
src_noms['code_quartier'] = src_noms['code_quartier'].astype(int)
noms_qu = src_noms.drop_duplicates('code_quartier')
df_quartier = df_quartier.merge(noms_qu, on='code_quartier', how='left')
df_quartier = df_quartier.sort_values('code_quartier').reset_index(drop=True)

# df_fusion = niveau arrondissement (rétro-compatibilité avec la suite du script)
df_fusion = df_arr

print(f"\nShape fusion arrondissement : {df_fusion.shape}")
print(f"Shape fusion quartier       : {df_quartier.shape}")
print(f"Aperçu colonnes arr. : {list(df_fusion.columns)[:5]} ...")

# ==========================================================================
# 4. EXPORTS PARQUET & POSTGRESQL (TABLEAUX DE BORD)
# ==========================================================================
parquet_path = os.path.join(GOLD_OUTPUT_DIR, 'indicateur_services_quotidien.parquet')
df_fusion.to_parquet(parquet_path, index=False)
print(f'\n✓ Parquet arrondissement sauvegardé : {parquet_path}')

parquet_path_qu = os.path.join(GOLD_OUTPUT_DIR, 'indicateur_services_quotidien_quartier.parquet')
df_quartier.to_parquet(parquet_path_qu, index=False)
print(f'✓ Parquet quartier sauvegardé : {parquet_path_qu}')

try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.indicateur_services CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.indicateur_services_quartier CASCADE;"))
        conn.commit()

    df_fusion.to_sql('indicateur_services', engine, if_exists='replace', index=False, schema='gold')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE gold.indicateur_services ADD PRIMARY KEY (code_postal)"))
        conn.commit()

    df_quartier.to_sql('indicateur_services_quartier', engine, if_exists='replace', index=False, schema='gold')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE gold.indicateur_services_quartier ADD PRIMARY KEY (code_quartier)"))
        conn.commit()

    print(f'✓ PostgreSQL : gold.indicateur_services ({len(df_fusion)} lignes)')
    print(f'✓ PostgreSQL : gold.indicateur_services_quartier ({len(df_quartier)} lignes)')
except Exception as e:
    print(f'❌ PostgreSQL indisponible — export ignoré : {e}')

# ==========================================================================
# 5. EXPORT MONGODB (GÉOLOCALISATION SUR CARTE)
# ==========================================================================
print("\n--- INSERTION DES DOCUMENTS GEOMETRIQUES PROPRES DANS MONGODB ---")

# --- 5.1 Écoles ---
df_ecoles_geo = df_ecoles.dropna(subset=['lat', 'lon']).copy()
df_ecoles_geo['type'] = 'ecole'
df_ecoles_geo['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(df_ecoles_geo['lon'], df_ecoles_geo['lat'])
]
for c in ['code_quartier', 'nom_quartier']:
    if c not in df_ecoles_geo.columns:
        df_ecoles_geo[c] = None
df_ecoles_geo['code_quartier'] = df_ecoles_geo['code_quartier'].apply(
    lambda v: int(v) if pd.notna(v) else None
)
cols_keep_ecoles = ['code_postal', 'code_quartier', 'nom_quartier', 'etablissement_nom', 'type', 'geo']
ecoles_docs = df_ecoles_geo[cols_keep_ecoles].to_dict(orient='records')

# --- 5.2 Commissariats ---
df_commis_geo = df_commis.dropna(subset=['lat', 'lon']).copy()
df_commis_geo['type'] = 'commissariat'
df_commis_geo['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(df_commis_geo['lon'], df_commis_geo['lat'])
]
for c in ['code_quartier', 'nom_quartier']:
    if c not in df_commis_geo.columns:
        df_commis_geo[c] = None
df_commis_geo['code_quartier'] = df_commis_geo['code_quartier'].apply(
    lambda v: int(v) if pd.notna(v) else None
)
cols_keep_commis = ['code_postal', 'code_quartier', 'nom_quartier', 'commissariat_nom', 'type_commissariat', 'type', 'geo']
commis_docs = df_commis_geo[cols_keep_commis].to_dict(orient='records')

# Note : Les commerces ne sont pas envoyés car ils n'ont pas de coordonnées (agrégés par ardt).

def insert_ecoles():
    if ecoles_docs:
        mongo['indicateur_services_geo'].insert_many(ecoles_docs, ordered=False)

def insert_commissariats():
    if commis_docs:
        mongo['indicateur_services_geo'].insert_many(commis_docs, ordered=False)

try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    
    # On vide la collection avant de la recréer
    mongo['indicateur_services_geo'].drop()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_ecoles = executor.submit(insert_ecoles)
        future_commis = executor.submit(insert_commissariats)
        future_ecoles.result()
        future_commis.result()

    print(f'✓ MongoDB : Écoles ajoutées ({len(ecoles_docs)} documents)')
    print(f'✓ MongoDB : Commissariats ajoutés ({len(commis_docs)} documents)')

    # Création de l'index géospatial
    mongo['indicateur_services_geo'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_services_geo'].create_index([("code_postal", 1)])
    mongo['indicateur_services_geo'].create_index([("code_quartier", 1)])
    print('✓ MongoDB : Index 2dsphere + code_postal + code_quartier créés avec succès.')

except Exception as e:
    print(f'❌ MongoDB indisponible — export géospatial ignoré : {e}')

print('\n=== FUSION SERVICES DU QUOTIDIEN TERMINÉE ===')