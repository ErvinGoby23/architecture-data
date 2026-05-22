import pandas as pd
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient

SILVER_DIR  = '../../silver/Score de connectivité/'
GOLD_DIR    = '../../gold/Score de connectivité/'
PG_URL      = 'postgresql://postgres:postgres@localhost:5432/postgres'
MONGO_URL   = 'mongodb://localhost:27017'
MONGO_DB    = 'urban_data'
os.makedirs(GOLD_DIR, exist_ok=True)

df_fibre    = pd.read_parquet(SILVER_DIR + 'fibre_paris_silver.parquet')
df_antennes = pd.read_parquet(SILVER_DIR + 'antennes_paris_silver.parquet')

df = df_fibre.merge(df_antennes, on='code_arrondissement', how='inner')
print(f'Jointure : {len(df)} arrondissements')

df['note_fibre']    = (df['taux_fibre_pct'] / 10).round(2)
df['note_antennes'] = (df['nb_antennes']    / df['nb_antennes'].max()    * 10).round(2)
df['note_4g']       = (df['nb_antennes_4g'] / df['nb_antennes_4g'].max() * 10).round(2)
df['note_5g']       = (df['nb_antennes_5g'] / df['nb_antennes_5g'].max() * 10).round(2)
df['score_mobile']       = ((df['note_antennes'] + df['note_4g'] + df['note_5g']) / 3).round(2)
df['score_connectivite'] = ((df['note_fibre'] + df['score_mobile']) / 2).round(2)

df_gold = df[['code_arrondissement', 'nom_arrondissement',
              'taux_fibre_pct', 'note_fibre',
              'nb_antennes', 'nb_antennes_4g', 'nb_antennes_5g',
              'note_antennes', 'note_4g', 'note_5g',
              'score_mobile', 'operateur_leader',
              'score_connectivite']].copy()

print(df_gold.sort_values('score_connectivite', ascending=False).to_string(index=False))

parquet_path = GOLD_DIR + 'score_connectivite_gold.parquet'
df_gold.to_parquet(parquet_path, index=False)
print(f'\n✓ Parquet : {parquet_path}')

engine = create_engine(PG_URL)
with engine.connect() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
    conn.commit()

df_gold.to_sql('score_connectivite', engine, if_exists='replace', index=False, schema='gold')
print(f'✓ PostgreSQL : table gold.score_connectivite ({len(df_gold)} lignes)')

client = MongoClient(MONGO_URL)
collection = client[MONGO_DB]['score_connectivite']
collection.drop()
collection.insert_many(df_gold.to_dict(orient='records'))
print(f'✓ MongoDB : collection score_connectivite ({len(df_gold)} documents)')

print('\n=== GOLD connectivité OK ===')