"""
FUSION (GOLD) — Indicateurs de logement
========================================
Fusionne les 3 sources Silver de l'indicateur logement en une table unique
par (arrondissement, année), prête pour l'API et le dashboard.

Sources Silver :
  - DVF        : prix au m² médian, volume de ventes        (clé arrondissement × année)
  - Logements sociaux : logements financés + ventilation     (clé arrondissement × année)
  - FILOSOFI   : revenus & pauvreté (millésime 2021 unique)   (clé arrondissement seul)

Stratégie de jointure :
  - DVF ⟕ LS sur (arrondissement, année)            -> ossature temporelle
  - FILOSOFI joint en BROADCAST sur 'arrondissement' (photo 2021 répliquée sur
    toutes les années), exactement comme une source agrégée non temporelle.

Indicateur dérivé (accessibilité financière, demandé par le brief) :
  - taux_effort_achat = prix d'un T3 type (~60 m²) / revenu médian annuel
    -> nombre d'années de revenu nécessaires pour acheter un 60 m².
"""

import os
import sys
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ==========================================================================
# 0. CONFIG & CHEMINS (ancrés sur l'emplacement du script)
# ==========================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.normpath(os.path.join(BASE_DIR, "..", "..", "..", ".env")))

GOLD_OUTPUT_DIR = os.path.join(BASE_DIR, "indicateur_logement")
os.makedirs(GOLD_OUTPUT_DIR, exist_ok=True)

PG_URL = os.getenv("PG_URL")

print("=== EXÉCUTION DU SCRIPT DE FUSION (GOLD) : INDICATEURS DE LOGEMENT ===")

# Date pour pointer le bon dossier daté (si pipeline planifié), sinon aujourd'hui
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")

# Les 3 Silver sont écrits à côté des scripts silver_*.py dans indicateur5/.
# On les cherche d'abord à plat, puis dans un sous-dossier daté si présent.
SILVER_DIR = BASE_DIR

PATHS = {
    "dvf": "dvf_silver.parquet",
    "ls": "logements_sociaux_silver.parquet",
    "filosofi": "filosofi_silver.parquet",
}


def resolve_silver(filename: str) -> str:
    """Trouve un parquet Silver : à plat, sinon dans un sous-dossier daté."""
    flat = os.path.join(SILVER_DIR, filename)
    if os.path.isfile(flat):
        return flat
    dated = os.path.join(SILVER_DIR, date_str, filename)
    if os.path.isfile(dated):
        return dated
    # repli : sous-dossier daté le plus récent contenant le fichier
    if os.path.isdir(SILVER_DIR):
        for d in sorted(os.listdir(SILVER_DIR), reverse=True):
            cand = os.path.join(SILVER_DIR, d, filename)
            if os.path.isfile(cand):
                print(f"   ↳ {filename} : bascule sur {d}")
                return cand
    return flat  # laissera read_parquet lever une erreur claire


# ==========================================================================
# 1. LECTURE DES SOURCES SILVER
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")

df_dvf = pd.read_parquet(resolve_silver(PATHS["dvf"]))
df_ls = pd.read_parquet(resolve_silver(PATHS["ls"]))
df_filo = pd.read_parquet(resolve_silver(PATHS["filosofi"]))

print(f"DVF       : {df_dvf.shape}")
print(f"Logements sociaux : {df_ls.shape}")
print(f"FILOSOFI  : {df_filo.shape}")

# ==========================================================================
# 2. PRÉPARATION — uniformisation des clés
# ==========================================================================
# DVF et LS portent déjà 'arrondissement' + 'annee'.
# FILOSOFI ne porte que 'arrondissement' (millésime unique) -> broadcast.

# On retire la 'cle' textuelle de chaque source pour la recalculer après fusion
for d in (df_dvf, df_ls, df_filo):
    if "cle" in d.columns:
        d.drop(columns=["cle"], inplace=True)

# FILOSOFI : on garde le millésime sous un nom explicite, on retire l'année implicite
df_filo = df_filo.rename(columns={"millesime": "filosofi_millesime"})

# ==========================================================================
# 3. FUSION — ossature temporelle (arrondissement × année)
# ==========================================================================
# Outer join DVF/LS pour ne perdre aucune (arrondissement, année) présente
# dans l'une OU l'autre source.
df_gold = df_dvf.merge(
    df_ls,
    on=["arrondissement", "annee"],
    how="outer",
)

# FILOSOFI en broadcast : jointure sur 'arrondissement' seul.
# Chaque ligne (arr, année) reçoit la photo socio-éco 2021 de son arrondissement.
df_gold = df_gold.merge(
    df_filo,
    on="arrondissement",
    how="left",
)

# ==========================================================================
# 4. INDICATEUR DÉRIVÉ — accessibilité financière (brief)
# ==========================================================================
# Coût d'un logement "type" de 60 m² rapporté au revenu médian annuel.
# = nombre d'années de revenu médian pour acheter ce bien dans l'arrondissement.
SURFACE_REF = 60  # m² (T3 de référence)
df_gold["prix_bien_60m2"] = (df_gold["prix_m2_median"] * SURFACE_REF).round(0)
df_gold["taux_effort_achat"] = (
    df_gold["prix_bien_60m2"] / df_gold["revenu_median"]
).round(1)

# ==========================================================================
# 5. NETTOYAGE FINAL & CLÉ COMPOSITE
# ==========================================================================
df_gold = df_gold[df_gold["arrondissement"].between(1, 20)]
df_gold = df_gold.dropna(subset=["arrondissement", "annee"])
df_gold["arrondissement"] = df_gold["arrondissement"].astype(int)
df_gold["annee"] = df_gold["annee"].astype(int)

# Colonnes de comptage : NaN -> 0 (absence = aucun logement social financé cette année)
count_cols = ["nb_ventes", "nb_logements", "nb_plai", "nb_plus",
              "nb_plus_cd", "nb_pls", "nb_programmes"]
for c in count_cols:
    if c in df_gold.columns:
        df_gold[c] = df_gold[c].fillna(0).astype(int)

# CLÉ COMPOSITE finale — table temporelle => arrondissement + année
df_gold["cle"] = (
    df_gold["arrondissement"].map("{:02d}".format)
    + "_"
    + df_gold["annee"].astype(str)
)

# Ordre des colonnes : clés en tête
front = ["cle", "arrondissement", "annee"]
rest = [c for c in df_gold.columns if c not in front]
df_gold = df_gold[front + rest].sort_values(
    ["arrondissement", "annee"]
).reset_index(drop=True)

print(f"\nShape table Gold : {df_gold.shape}")
print(f"Période couverte : {df_gold['annee'].min()} → {df_gold['annee'].max()}")
print(f"Arrondissements  : {df_gold['arrondissement'].nunique()}")
print(f"Colonnes : {list(df_gold.columns)}")
print(df_gold.head(6).to_string(index=False))

# ==========================================================================
# 6. EXPORTS — PARQUET & POSTGRESQL
# ==========================================================================
parquet_path = os.path.join(GOLD_OUTPUT_DIR, "indicateur_logement.parquet")
df_gold.to_parquet(parquet_path, index=False)
print(f"\n✓ Parquet sauvegardé : {parquet_path}")

if PG_URL:
    try:
        engine = create_engine(PG_URL)
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(text("DROP TABLE IF EXISTS gold.indicateur_logement CASCADE;"))
            conn.commit()

        df_gold.to_sql("indicateur_logement", engine,
                       if_exists="replace", index=False, schema="gold")
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE gold.indicateur_logement ADD PRIMARY KEY (cle)"
            ))
            conn.commit()

        print(f"✓ PostgreSQL : gold.indicateur_logement ({len(df_gold)} lignes)")
    except Exception as e:
        print(f"❌ PostgreSQL indisponible — export ignoré : {e}")
else:
    print("ℹ PG_URL absent du .env — export PostgreSQL ignoré.")

print("\n=== FUSION INDICATEURS DE LOGEMENT TERMINÉE ===")
