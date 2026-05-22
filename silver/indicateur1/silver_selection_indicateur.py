import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient

load_dotenv('../../.env')

SILVER     = 'nettoyage-indicateur1'
SILVER_DIR = '../../silver/indicateur1/'
PG_URL     = os.getenv('PG_URL')
MONGO_URL  = os.getenv('MONGO_URL')
MONGO_DB   = 'silver'
os.makedirs(SILVER, exist_ok=True)
os.makedirs(SILVER_DIR, exist_ok=True)

df_arrets = pd.read_csv(f'{SILVER}/arrets_lignes_final_paris.csv', sep=';')
df_taxi   = pd.read_csv(f'{SILVER}/bornes_taxi_final_paris.csv', sep=';')
df_stat   = pd.read_csv(f'{SILVER}/stationnement_final_paris.csv', sep=';')

cols_arrets = ['code_postal', 'stop_id', 'stop_lat', 'stop_lon', 'route_type', 'route_short_name']
cols_taxi   = ['code_postal', 'borne_id', 'lat', 'lon', 'nb_emplacements']
cols_stat   = ['code_postal', 'nb_places_reelles', 'regime_category']

df_arrets = df_arrets[[c for c in cols_arrets if c in df_arrets.columns]]
df_taxi   = df_taxi[[c for c in cols_taxi     if c in df_taxi.columns]]
df_stat   = df_stat[[c for c in cols_stat     if c in df_stat.columns]]

df_stat = df_stat[df_stat['regime_category'].notna()].copy()

def count_unique_stops(x):
    return x.nunique()

def count_unique_lines(x):
    return x.nunique()

def count_unique_modes(x):
    return x.nunique()

def sum_emplacements(x):
    return x.sum()

def sum_places(x):
    return x.sum()

agg_arrets = df_arrets.groupby('code_postal').agg(
    nb_arrets = ('stop_id',          count_unique_stops),
    nb_lignes = ('route_short_name', count_unique_lines),
    nb_modes  = ('route_type',       count_unique_modes),
).reset_index()

agg_taxi = df_taxi.groupby('code_postal').agg(
    nb_bornes            = ('borne_id',        'count'),
    nb_emplacements_taxi = ('nb_emplacements', sum_emplacements),
).reset_index()

df_stat_gratuit    = df_stat[df_stat['regime_category'] == 'gratuit'].groupby('code_postal').agg(nb_places_gratuit    = ('nb_places_reelles', sum_places)).reset_index()
df_stat_payant     = df_stat[df_stat['regime_category'] == 'payant'].groupby('code_postal').agg(nb_places_payant     = ('nb_places_reelles', sum_places)).reset_index()
df_stat_2roues     = df_stat[df_stat['regime_category'] == '2roues'].groupby('code_postal').agg(nb_places_2roues     = ('nb_places_reelles', sum_places)).reset_index()
df_stat_pmr        = df_stat[df_stat['regime_category'] == 'pmr'].groupby('code_postal').agg(nb_places_pmr        = ('nb_places_reelles', sum_places)).reset_index()
df_stat_electrique = df_stat[df_stat['regime_category'] == 'electrique'].groupby('code_postal').agg(nb_places_electrique = ('nb_places_reelles', sum_places)).reset_index()

agg_stat = df_stat_gratuit.merge(df_stat_payant,     on='code_postal', how='outer')
agg_stat = agg_stat.merge(df_stat_2roues,            on='code_postal', how='outer')
agg_stat = agg_stat.merge(df_stat_pmr,               on='code_postal', how='outer')
agg_stat = agg_stat.merge(df_stat_electrique,        on='code_postal', how='outer')

df_fusion = agg_arrets.merge(agg_taxi, on='code_postal', how='outer')
df_fusion = df_fusion.merge(agg_stat,  on='code_postal', how='outer')
df_fusion = df_fusion.fillna(0)

df_fusion['arrondissement'] = df_fusion['code_postal'].astype(int) - 75000
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)

print(f"Shape fusion : {df_fusion.shape}")
print(df_fusion.to_string(index=False))

parquet_path = f'{SILVER}/indicateur_mobilite_silver.parquet'
df_fusion.to_parquet(parquet_path, index=False)
print(f'✓ Parquet : {parquet_path}')

engine = create_engine(PG_URL)
with engine.connect() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
    conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_mobilite CASCADE;"))
    conn.commit()

df_fusion.to_sql('indicateur_mobilite', engine, if_exists='replace', index=False, schema='silver')
print(f'✓ PostgreSQL : table silver.indicateur_mobilite ({len(df_fusion)} lignes)')

client = MongoClient(MONGO_URL)
client.drop_database('silver')
mongo = client[MONGO_DB]

def make_geo_point(lon, lat):
    return {'type': 'Point', 'coordinates': [float(lon), float(lat)]}

df_arrets_valid = df_arrets.dropna(subset=['stop_lat', 'stop_lon']).copy()
df_taxi_valid   = df_taxi.dropna(subset=['lat', 'lon']).copy()

arrets_docs = [
    {
        'code_postal' : int(r.code_postal),
        'type'        : 'arret',
        'stop_id'     : r.stop_id,
        'geo'         : make_geo_point(r.stop_lon, r.stop_lat)
    }
    for r in df_arrets_valid.itertuples()
]

taxi_docs = [
    {
        'code_postal' : int(r.code_postal),
        'type'        : 'borne_taxi',
        'borne_id'    : r.borne_id,
        'geo'         : make_geo_point(r.lon, r.lat)
    }
    for r in df_taxi_valid.itertuples()
]

docs_mongo = arrets_docs + taxi_docs
mongo['indicateur_mobilite'].insert_many(docs_mongo)
print(f'✓ MongoDB Atlas : collection indicateur_mobilite ({len(docs_mongo)} documents)')
print(f'   dont arrets     : {len(arrets_docs)}')
print(f'   dont bornes taxi: {len(taxi_docs)}')

print('\n=== SILVER mobilité OK ===')