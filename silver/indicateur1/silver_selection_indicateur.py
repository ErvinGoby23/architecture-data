"""
silver_selection_indicateur1.py
Sélection des colonnes utiles pour l'indicateur mobilité
Sources : 3 fichiers nettoyés Silver
Output  : 3 fichiers allégés dans nettoyage-indicateur1/
"""

import pandas as pd
import os

SILVER = 'nettoyage-indicateur1'
os.makedirs(SILVER, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════
# 1. ARRÊTS & LIGNES
# ══════════════════════════════════════════════════════════════════════════
print("📥 Arrêts & lignes...")
df = pd.read_csv(f'{SILVER}/arrets_lignes_final_paris.csv', sep=';')
print(f"   Shape entrée : {df.shape}")
print(f"   Colonnes dispo : {list(df.columns)}")

cols = ['code_postal', 'arrondissement', 'stop_id', 'stop_lat', 'stop_lon',
        'route_type', 'route_short_name']
cols = [c for c in cols if c in df.columns]
df = df[cols]

df.to_parquet(f'{SILVER}/arrets_lignes_select.parquet', index=False)
print(f"   Shape sortie  : {df.shape}")
print(f"   Colonnes      : {list(df.columns)}")

# ══════════════════════════════════════════════════════════════════════════
# 2. BORNES TAXI
# ══════════════════════════════════════════════════════════════════════════
print("\n📥 Bornes taxi...")
df = pd.read_csv(f'{SILVER}/bornes_taxi_final_paris.csv', sep=';')
print(f"   Shape entrée : {df.shape}")
print(f"   Colonnes dispo : {list(df.columns)}")

cols = ['code_postal', 'arrondissement', 'borne_id', 'lat', 'lon',
        'nb_emplacements']
cols = [c for c in cols if c in df.columns]
df = df[cols]

df.to_parquet(f'{SILVER}/bornes_taxi_select.parquet', index=False)
print(f"   Shape sortie  : {df.shape}")
print(f"   Colonnes      : {list(df.columns)}")

# ══════════════════════════════════════════════════════════════════════════
# 3. STATIONNEMENT
# ══════════════════════════════════════════════════════════════════════════
print("\n📥 Stationnement...")
df = pd.read_csv(f'{SILVER}/stationnement_final_paris.csv', sep=';')
print(f"   Shape entrée : {df.shape}")
print(f"   Colonnes dispo : {list(df.columns)}")

cols = ['code_postal', 'arrondissement', 'nb_places_reelles',
        'regime_prioritaire', 'localisation']
cols = [c for c in cols if c in df.columns]
df = df[cols]

df.to_parquet(f'{SILVER}/stationnement_select.parquet', index=False)
print(f"   Shape sortie  : {df.shape}")
print(f"   Colonnes      : {list(df.columns)}")

print("\n✅ Sélection terminée — 3 fichiers dans nettoyage-indicateur1/")
print("   arrets_lignes_select.parquet")
print("   bornes_taxi_select.parquet")
print("   stationnement_select.parquet")

# ══════════════════════════════════════════════════════════════════════════
# 4. FUSION DES 3 EN UN SEUL PARQUET
# ══════════════════════════════════════════════════════════════════════════
print("\n🔗 Fusion des 3 datasets...")

df_arrets = pd.read_parquet(f'{SILVER}/arrets_lignes_select.parquet')
df_taxi   = pd.read_parquet(f'{SILVER}/bornes_taxi_select.parquet')
df_stat   = pd.read_parquet(f'{SILVER}/stationnement_select.parquet')

# Agrégation par code_postal avant fusion
agg_arrets = df_arrets.groupby('code_postal').agg(
    nb_arrets  = ('stop_id',          'nunique'),
    nb_lignes  = ('route_short_name', 'nunique'),
    nb_modes   = ('route_type',       'nunique'),
).reset_index()

agg_taxi = df_taxi.groupby('code_postal').agg(
    nb_bornes            = ('borne_id',       'count'),
    nb_emplacements_taxi = ('nb_emplacements', 'sum'),
).reset_index()

agg_stat = df_stat.groupby('code_postal').agg(
    nb_places_total = ('nb_places_reelles', 'sum'),
).reset_index()

# Fusion sur code_postal
df_fusion = agg_arrets.merge(agg_taxi, on='code_postal', how='outer')
df_fusion = df_fusion.merge(agg_stat,  on='code_postal', how='outer')
df_fusion = df_fusion.fillna(0)

# Ajout arrondissement
df_fusion['arrondissement'] = df_fusion['code_postal'].astype(int) - 75000
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)

df_fusion.to_parquet(f'{SILVER}/indicateur_mobilite_silver.parquet', index=False)
print(f"✅ Fusion créée : {SILVER}/indicateur_mobilite_silver.parquet")
print(f"   Shape : {df_fusion.shape}")
print(f"   Colonnes : {list(df_fusion.columns)}")
print(df_fusion.to_string(index=False))
