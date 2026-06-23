import pandas as pd
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE
from datetime import datetime

load_dotenv('../../../.env')

# On suppose que l'on est sur l'Indicateur 4 (Services du quotidien)
GOLD_OUTPUT_DIR = 'indicateur_services'
os.makedirs(GOLD_OUTPUT_DIR, exist_ok=True)

print("=== EXÉCUTION DU SCRIPT DE FUSION (GOLD) : SERVICES DU QUOTIDIEN ===")

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver' # Ou 'gold' selon ton architecture

# ==========================================================================
# 1. LECTURE PARQUET (Sources Silver)
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")

import sys
from datetime import datetime

# On récupère la date pour pointer vers le bon dossier
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

# On ajoute le {date_str} au chemin
PATH_ECOLES = f'nettoyage-indicateur1/{date_str}/ecoles_elementaires_paris_silver.parquet'

# Les autres chemins ne changent pas car on n'a pas mis de date
PATH_COMMIS = 'nettoyage-indicateur-commissariats/commissariats_paris_silver.parquet'
PATH_COMMER = 'nettoyage-indicateur-commerces/commerces_paris_silver.parquet'

df_ecoles = pd.read_parquet(PATH_ECOLES)
df_commis = pd.read_parquet(PATH_COMMIS)
df_commer = pd.read_parquet(PATH_COMMER)

print(f"Écoles        : {df_ecoles.shape}")
print(f"Commissariats : {df_commis.shape}")
print(f"Commerces     : {df_commer.shape}")

# ==========================================================================
# 2. PRÉPARATION ET AGRÉGATION
# ==========================================================================

# --- A. Écoles ---
agg_ecoles = df_ecoles.groupby('code_postal').agg(
    nb_ecoles = ('etablissement_nom', 'nunique')
).reset_index()

# --- B. Commissariats ---
agg_commis = df_commis.groupby('code_postal').agg(
    nb_commissariats = ('commissariat_nom', 'nunique')
).reset_index()

# --- C. Commerces ---
# Conversion Code INSEE (751xx) -> Code Postal (750xx)
df_commer['code_postal'] = df_commer['code_insee'].astype(int) - 100

# On additionne toutes les colonnes numériques pour avoir le total des commerces
# (On exclut le code_insee, code_postal, et population si elle existe)
cols_to_sum = [c for c in df_commer.columns if c not in ['code_insee', 'code_postal', 'commune_nom', 'population_2010']]
df_commer['nb_commerces_total'] = df_commer[cols_to_sum].sum(axis=1)

agg_commer = df_commer[['code_postal', 'nb_commerces_total'] + cols_to_sum].copy()

# ==========================================================================
# 3. FUSION GLOBALE (MERGE)
# ==========================================================================
df_fusion = agg_ecoles.merge(agg_commis, on='code_postal', how='outer')
df_fusion = df_fusion.merge(agg_commer,  on='code_postal', how='outer')

# On remplace les valeurs manquantes par 0 (ex: s'il n'y a pas de commissariat dans le 2e ardt)
df_fusion = df_fusion.fillna(0)

# Convertir en entier pour que ce soit propre
cols_int = [c for c in df_fusion.columns if c != 'code_postal']
df_fusion[cols_int] = df_fusion[cols_int].astype(int)
df_fusion['code_postal'] = df_fusion['code_postal'].astype(int)

df_fusion = df_fusion.sort_values('code_postal').reset_index(drop=True)

print(f"\nShape fusion : {df_fusion.shape}")
print(f"Aperçu des colonnes : {list(df_fusion.columns)[:5]} ...")

# ==========================================================================
# 4. EXPORTS PARQUET & POSTGRESQL (TABLEAUX DE BORD)
# ==========================================================================
parquet_path = os.path.join(GOLD_OUTPUT_DIR, 'indicateur_services_quotidien.parquet')
df_fusion.to_parquet(parquet_path, index=False)
print(f'\n✓ Parquet final sauvegardé dans : {parquet_path}')

try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.indicateur_services CASCADE;"))
        conn.commit()
    
    df_fusion.to_sql('indicateur_services', engine, if_exists='replace', index=False, schema='gold')
    
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE gold.indicateur_services ADD PRIMARY KEY (code_postal)"))
        conn.commit()
    print(f'✓ PostgreSQL : table gold.indicateur_services mise à jour ({len(df_fusion)} lignes)')
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
cols_keep_ecoles = ['code_postal', 'etablissement_nom', 'type', 'geo']
ecoles_docs = df_ecoles_geo[cols_keep_ecoles].to_dict(orient='records')

# --- 5.2 Commissariats ---
df_commis_geo = df_commis.dropna(subset=['lat', 'lon']).copy()
df_commis_geo['type'] = 'commissariat'
df_commis_geo['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(df_commis_geo['lon'], df_commis_geo['lat'])
]
cols_keep_commis = ['code_postal', 'commissariat_nom', 'type_commissariat', 'type', 'geo']
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
    print('✓ MongoDB : Index 2dsphere créé avec succès.')

except Exception as e:
    print(f'❌ MongoDB indisponible — export géospatial ignoré : {e}')

print('\n=== FUSION SERVICES DU QUOTIDIEN TERMINÉE ===')