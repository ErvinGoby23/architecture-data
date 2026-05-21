"""
gold_indicateur_mobilite.py
Calcul du score de mobilité par arrondissement
Source : ../silver/indicateur1/nettoyage-indicateur1/indicateur_mobilite_silver.parquet
Output : gold/indicateur1/indicateur_mobilite.parquet
"""

import pandas as pd
import numpy as np
import os

SILVER = '../../silver/indicateur1/nettoyage-indicateur1'
GOLD   = '.'
os.makedirs(GOLD, exist_ok=True)

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement Silver...")
df = pd.read_parquet(f'{SILVER}/indicateur_mobilite_silver.parquet')
print(f"   Shape : {df.shape}")
print(df.to_string(index=False))

# ── 2. Normalisation 0-1 ──────────────────────────────────────────────────
print("\n🧮 Normalisation des composantes...")

def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)

df['score_arrets']        = normalize(df['nb_arrets'])
df['score_lignes']        = normalize(df['nb_lignes'])
df['score_modes']         = normalize(df['nb_modes'])
df['score_taxi']          = normalize(df['nb_bornes'])
df['score_stationnement'] = normalize(df['nb_places_total'])

# ── 3. Score final pondéré ────────────────────────────────────────────────
print("📊 Calcul du score final...")
df['score_mobilite'] = (
    df['score_arrets']        * 0.30 +
    df['score_lignes']        * 0.25 +
    df['score_modes']         * 0.15 +
    df['score_taxi']          * 0.15 +
    df['score_stationnement'] * 0.15
).round(4)

# ── 4. Export ─────────────────────────────────────────────────────────────
output = f'{GOLD}/indicateur_mobilite.parquet'
df.to_parquet(output, index=False)
print(f"\n✅ Export : {output}")
print(f"   Shape  : {df.shape}")

# ── 5. Résumé ─────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SCORE MOBILITÉ PAR ARRONDISSEMENT")
print("="*60)
cols = ['arrondissement', 'code_postal', 'nb_arrets', 'nb_lignes',
        'nb_modes', 'nb_bornes', 'nb_places_total', 'score_mobilite']
print(df[cols].sort_values('score_mobilite', ascending=False).to_string(index=False))

print(f"\n🏆 Meilleur   : {df.loc[df['score_mobilite'].idxmax(), 'arrondissement']}e arrondissement")
print(f"📉 Moins bien : {df.loc[df['score_mobilite'].idxmin(), 'arrondissement']}e arrondissement")
