"""
gold_indicateur_mobilite.py
Calcul du score de mobilité par arrondissement normalisé par superficie
Source : ../../silver/indicateur1/nettoyage-indicateur1/indicateur_mobilite_silver.parquet
         ../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv
Output : ./indicateur_mobilite.parquet
"""

import pandas as pd
import numpy as np
import os

SILVER = '../../silver/indicateur1/nettoyage-indicateur1'
BRUTE  = '../../brute/indicateur-Score-accessibilité-mobilité'
GOLD   = '.'

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement Silver...")
df = pd.read_parquet(f'{SILVER}/indicateur_mobilite_silver.parquet')
print(f"   Shape : {df.shape}")

# ── 2. Chargement superficie arrondissements ───────────────────────────────
print("\n📐 Chargement superficie arrondissements...")
df_arr = pd.read_csv(f'{BRUTE}/arrondissements.csv', sep=';')
print(f"   Colonnes : {list(df_arr.columns)}")

# Détecter colonne superficie et numéro arrondissement
col_surface = next((c for c in df_arr.columns if 'surface' in c.lower()), None)
col_num     = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
print(f"   Surface : {col_surface}")
print(f"   Num arr : {col_num}")

df_surface = df_arr[[col_num, col_surface]].copy()
df_surface.columns = ['arrondissement', 'surface_m2']

# Surface en km²
df_surface['surface_km2'] = df_surface['surface_m2'] / 1_000_000

# Merge avec le dataset Gold
df = df.merge(df_surface, on='arrondissement', how='left')
print(f"\n   Surface par arrondissement :")
print(df[['arrondissement', 'surface_km2']].to_string(index=False))

# ── 3. Normalisation par superficie ───────────────────────────────────────
print("\n📊 Normalisation par superficie (par km²)...")
df['nb_arrets_par_km2']  = (df['nb_arrets']       / df['surface_km2']).round(2)
df['nb_lignes_par_km2']  = (df['nb_lignes']        / df['surface_km2']).round(2)
df['nb_bornes_par_km2']  = (df['nb_bornes']        / df['surface_km2']).round(2)
df['nb_places_par_km2']  = (df['nb_places_total']  / df['surface_km2']).round(2)

print(df[['arrondissement', 'nb_arrets_par_km2', 'nb_bornes_par_km2', 'nb_places_par_km2']].to_string(index=False))

# ── 4. Score final normalisé par km² ──────────────────────────────────────
print("\n🧮 Calcul du score final normalisé...")

def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)

df['score_arrets']        = normalize(df['nb_arrets_par_km2'])
df['score_lignes']        = normalize(df['nb_lignes_par_km2'])
df['score_modes']         = normalize(df['nb_modes'])
df['score_taxi']          = normalize(df['nb_bornes_par_km2'])
df['score_stationnement'] = normalize(df['nb_places_par_km2'])

df['score_mobilite'] = (
    df['score_arrets']        * 0.30 +
    df['score_lignes']        * 0.25 +
    df['score_modes']         * 0.15 +
    df['score_taxi']          * 0.15 +
    df['score_stationnement'] * 0.15
).round(4)

# ── 5. Export ─────────────────────────────────────────────────────────────
output = f'{GOLD}/indicateur_mobilite.parquet'
df.to_parquet(output, index=False)
print(f"\n✅ Export : {output}")
print(f"   Shape  : {df.shape}")
print(f"   Colonnes : {list(df.columns)}")

# ── 6. Résumé ─────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("SCORE MOBILITÉ PAR ARRONDISSEMENT (normalisé par superficie)")
print("="*65)
cols = ['arrondissement', 'code_postal', 'surface_km2',
        'nb_arrets_par_km2', 'nb_bornes_par_km2',
        'nb_places_par_km2', 'score_mobilite']
print(df[cols].sort_values('score_mobilite', ascending=False).to_string(index=False))

print(f"\n🏆 Meilleur   : {df.loc[df['score_mobilite'].idxmax(), 'arrondissement']}e arrondissement")
print(f"📉 Moins bien : {df.loc[df['score_mobilite'].idxmin(), 'arrondissement']}e arrondissement")
