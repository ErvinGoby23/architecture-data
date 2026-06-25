"""
silver_fusion_vivabilite.py — Fusion Score de Vivabilité (par arrondissement)
Urban Data Explorer · Silver layer
"""

import pandas as pd
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient

load_dotenv('../../../.env')

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
SILVER_DIR  = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(SILVER_DIR, exist_ok=True)

print("=== EXÉCUTION DU SCRIPT SILVER FUSION VIVABILITÉ ===")

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver'

# ==========================================================================
# 1. LECTURE DES PARQUETS SILVER
# ==========================================================================
print("\n--- CHARGEMENT DES DONNÉES SILVER ---")

df_criminalite  = pd.read_parquet(f'{SILVER_DIR}/criminalite_pivot_silver.parquet')
df_proprete     = pd.read_parquet(f'{SILVER_DIR}/proprete_agrege_silver.parquet')
df_espaces      = pd.read_parquet(f'{SILVER_DIR}/espaces_verts_agrege_silver.parquet')
df_bruit        = pd.read_parquet(f'{SILVER_DIR}/bruit_agrege_silver.parquet')
df_no2          = pd.read_parquet(f'{SILVER_DIR}/NO2_resume_silver.parquet')

print(f"Criminalité  (arrondissements) : {df_criminalite.shape}")
print(f"Propreté     (arrondissements) : {df_proprete.shape}")
print(f"Espaces verts(arrondissements) : {df_espaces.shape}")
print(f"Bruit        (agrégé annuel)   : {df_bruit.shape}")
print(f"NO2          (tronçons)        : {df_no2.shape}")

# ==========================================================================
# 2. PRÉPARATION — colonnes sélectionnées pour la fusion
# ==========================================================================

# Criminalité → taux moyens par indicateur par arrondissement
cols_crim = ['arrondissement', 'insee_pop'] + [c for c in df_criminalite.columns if c.startswith('taux_')]
df_crim_s = df_criminalite[[c for c in cols_crim if c in df_criminalite.columns]].copy()

# Propreté → nb signalements + score pondéré
cols_prop = ['arrondissement', 'nb_signalements', 'score_poids_total', 'poids_moyen']
df_prop_s = df_proprete[[c for c in cols_prop if c in df_proprete.columns]].copy()

# Espaces verts → surface totale + nb espaces
cols_ev = ['arrondissement', 'nb_espaces_verts']
if 'surface_totale_m2' in df_espaces.columns:
    cols_ev += ['surface_totale_m2', 'surface_moy_m2', 'nb_grands_espaces']
df_ev_s = df_espaces[[c for c in cols_ev if c in df_espaces.columns]].copy()

# Bruit → moyenne Lden et Ln (dernière année disponible)
lden_row = df_bruit[(df_bruit['type'] == 'Lden')].sort_values('annee', ascending=False).head(1)
ln_row   = df_bruit[(df_bruit['type'] == 'Ln')  ].sort_values('annee', ascending=False).head(1)
bruit_lden_moy = lden_row['valeur_moy'].values[0] if len(lden_row) else None
bruit_ln_moy   = ln_row['valeur_moy'].values[0]   if len(ln_row)   else None
print(f"\nBruit dernière année — Lden moyen : {bruit_lden_moy} dB | Ln moyen : {bruit_ln_moy} dB")

# NO2 → moyenne globale Périphérique (pas d'arrondissement)
no2_global_moy = df_no2['no2_moy_µg_m3'].mean().round(2)
no2_seuil_pct  = df_no2['pct_heures_oms'].mean().round(2)
print(f"NO2 Périphérique — moy : {no2_global_moy} µg/m³ | % > OMS : {no2_seuil_pct}%")

# ==========================================================================
# 3. FUSION PAR ARRONDISSEMENT
# ==========================================================================
print("\n--- FUSION PAR ARRONDISSEMENT ---")

# Base : arrondissements 1–20
df_fusion = pd.DataFrame({'arrondissement': range(1, 21)})

df_fusion = df_fusion.merge(df_crim_s, on='arrondissement', how='left')
df_fusion = df_fusion.merge(df_prop_s, on='arrondissement', how='left')
df_fusion = df_fusion.merge(df_ev_s,   on='arrondissement', how='left')

# Bruit et NO2 : valeurs globales répétées sur tous les arrondissements
df_fusion['bruit_lden_moy_db']   = bruit_lden_moy
df_fusion['bruit_ln_moy_db']     = bruit_ln_moy
df_fusion['no2_periphe_moy']     = no2_global_moy
df_fusion['no2_periphe_pct_oms'] = no2_seuil_pct

df_fusion = df_fusion.fillna(0)
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)

print(f"Shape fusion finale : {df_fusion.shape}")
print(f"Arrondissements couverts : {df_fusion['arrondissement'].nunique()}")

# ==========================================================================
# 4. CALCUL SCORE VIVABILITÉ (normalisé 0–100)
# ==========================================================================
print("\n--- CALCUL SCORE VIVABILITÉ ---")

def minmax(series, inverse=False):
    """Normalise une série entre 0 et 100. inverse=True si valeur haute = mauvais."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 100
    return 100 - norm if inverse else norm

# Score propreté : inverse (plus de signalements = moins propre)
if 'score_poids_total' in df_fusion.columns:
    df_fusion['score_proprete'] = minmax(df_fusion['score_poids_total'], inverse=True).round(2)

# Score espaces verts : surface totale (direct)
if 'surface_totale_m2' in df_fusion.columns:
    df_fusion['score_espaces_verts'] = minmax(df_fusion['surface_totale_m2']).round(2)
elif 'nb_espaces_verts' in df_fusion.columns:
    df_fusion['score_espaces_verts'] = minmax(df_fusion['nb_espaces_verts']).round(2)

# Score criminalité : taux moyen global (inverse)
taux_cols = [c for c in df_fusion.columns if c.startswith('taux_')]
if taux_cols:
    df_fusion['taux_crime_global'] = df_fusion[taux_cols].mean(axis=1)
    df_fusion['score_criminalite'] = minmax(df_fusion['taux_crime_global'], inverse=True).round(2)

# Score bruit : constant (pas de variation par arrondissement dans ce dataset)
df_fusion['score_bruit'] = max(0, 100 - max(0, bruit_lden_moy - 50) * 3.33) if bruit_lden_moy else 50.0

# Score NO2 : constant (Périphérique, pas par arrondissement)
df_fusion['score_no2'] = max(0, 100 - no2_seuil_pct) if no2_seuil_pct else 50.0

# Score global vivabilité (moyenne pondérée)
score_cols_weights = {
    'score_proprete'      : 0.30,
    'score_espaces_verts' : 0.25,
    'score_criminalite'   : 0.25,
    'score_bruit'         : 0.10,
    'score_no2'           : 0.10,
}
available = {k: v for k, v in score_cols_weights.items() if k in df_fusion.columns}
total_weight = sum(available.values())

df_fusion['score_vivabilite'] = sum(
    df_fusion[col] * (w / total_weight)
    for col, w in available.items()
).round(2)

score_preview = df_fusion[['arrondissement', 'score_vivabilite'] + list(available.keys())].copy()
print(score_preview.to_string(index=False))

# ==========================================================================
# 5. EXPORTS PARQUET
# ==========================================================================
out_fusion = os.path.join(SILVER_DIR, 'vivabilite_arrondissement_silver.parquet')
df_fusion.to_parquet(out_fusion, index=False)
print(f"\n✓ Parquet fusion : {out_fusion}")

# ==========================================================================
# 6. POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_vivabilite_arrondissement CASCADE;"))
        conn.commit()

    df_pg = df_fusion.copy()
    df_pg.to_sql('indicateur_vivabilite_arrondissement', engine,
                 if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_vivabilite_arrondissement ADD PRIMARY KEY (arrondissement)"))
        conn.commit()

    print(f"✓ PostgreSQL : silver.indicateur_vivabilite_arrondissement ({len(df_pg)} lignes)")
except Exception as e:
    print(f"❌ PostgreSQL indisponible : {e}")

# ==========================================================================
# 7. MONGODB
# ==========================================================================
print("\n--- INSERTION DANS MONGODB ---")
try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_vivabilite'].drop()

    docs = df_fusion.to_dict(orient='records')
    for doc in docs:
        # Conversion numpy types → python natifs
        for k, v in doc.items():
            if hasattr(v, 'item'):
                doc[k] = v.item()

    mongo['indicateur_vivabilite'].insert_many(docs)
    mongo['indicateur_vivabilite'].create_index([("arrondissement", 1)], unique=True)
    print(f"✓ MongoDB : {len(docs)} documents insérés (collection indicateur_vivabilite)")
    print("✓ MongoDB : Index arrondissement créé")
except Exception as e:
    print(f"❌ MongoDB indisponible : {e}")

# ==========================================================================
# 8. MONGODB — POINTS GÉOSPATIAUX (propreté + espaces verts)
# ==========================================================================
print("\n--- INSERTION DES POINTS GÉO DANS MONGODB ---")
try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_vivabilite_geo'].drop()

    docs_geo = []

    # --- Propreté : 1 doc par signalement avec lat/lon ---
    df_prop_long = pd.read_parquet(os.path.join(SILVER_DIR, 'proprete_long_silver.parquet'))
    df_prop_geo  = df_prop_long.dropna(subset=['latitude', 'longitude']).copy()

    for _, r in df_prop_geo.iterrows():
        docs_geo.append({
            'type'            : 'signalement',
            'arrondissement'  : int(r['arrondissement']) if pd.notna(r.get('arrondissement')) else None,
            'type_declaration': r.get('type_declaration', ''),
            'poids'           : int(r.get('poids', 1)),
            'geo'             : {
                'type'       : 'Point',
                'coordinates': [float(r['longitude']), float(r['latitude'])],
            },
        })

    print(f"  Signalements propreté : {len(docs_geo):,}")

    # --- Espaces verts : 1 doc par espace avec lat/lon ---
    df_ev_long = pd.read_parquet(os.path.join(SILVER_DIR, 'espaces_verts_long_silver.parquet'))
    df_ev_geo  = df_ev_long.dropna(subset=['latitude', 'longitude']).copy()

    ev_docs = []
    for _, r in df_ev_geo.iterrows():
        ev_docs.append({
            'type'            : 'espace_vert',
            'arrondissement'  : int(r['arrondissement']) if pd.notna(r.get('arrondissement')) else None,
            'nom'             : r.get('nom', ''),
            'type_espace_vert': r.get('type_espace_vert', ''),
            'surface_m2'      : float(r['surface_m2']) if pd.notna(r.get('surface_m2')) else None,
            'geo'             : {
                'type'       : 'Point',
                'coordinates': [float(r['longitude']), float(r['latitude'])],
            },
        })

    print(f"  Espaces verts : {len(ev_docs):,}")
    docs_geo += ev_docs

    # Insertion par batch de 10 000 pour éviter les timeouts
    batch_size = 10_000
    for i in range(0, len(docs_geo), batch_size):
        mongo['indicateur_vivabilite_geo'].insert_many(docs_geo[i:i+batch_size], ordered=False)

    from pymongo import GEOSPHERE
    mongo['indicateur_vivabilite_geo'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_vivabilite_geo'].create_index([("arrondissement", 1)])
    mongo['indicateur_vivabilite_geo'].create_index([("type", 1)])

    print(f"✓ MongoDB : {len(docs_geo):,} documents insérés (collection indicateur_vivabilite_geo)")
    print("✓ MongoDB : Index 2dsphere + arrondissement + type créés")
except Exception as e:
    print(f"❌ MongoDB GeoJSON indisponible : {e}")

print("\n=== SILVER vivabilité OK ===")
print(f"Colonnes finales ({len(df_fusion.columns)}) : {list(df_fusion.columns)}")
