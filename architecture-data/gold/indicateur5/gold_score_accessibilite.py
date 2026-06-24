"""
gold_score_accessibilite.py — Pipeline Gold · Indicateur 5 : Accessibilité du logement
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER

Sources Silver fusionnées :
  - DVF        : prix au m² médian, volume de ventes       (arr × année / quartier × année)
  - Logements sociaux : logements financés + ventilation    (arr × année / quartier × année)
  - FILOSOFI   : revenus & pauvreté (millésime 2021)         (arrondissement seul)

Choix méthodologiques (calqués sur le score de connectivité) :
- Score = combinaison normalisée de sous-scores, orienté "accessibilité"
  (un score élevé = logement plus accessible).
    * score_prix    : inverse du prix au m² (moins cher = plus accessible)
    * score_social  : densité de logements sociaux financés (plus = plus accessible)
    * score_revenu  : capacité d'achat = revenu médian / prix au m²
- ARRONDISSEMENT : score_prix 0.40 + score_social 0.25 + score_revenu 0.35
- QUARTIER       : score_prix 0.60 + score_social 0.40
    → le revenu (FILOSOFI) n'existe qu'à la maille arrondissement ; on l'exclut
      du score quartier pour éviter un biais de nivellement intra-arrondissement,
      exactement comme la fibre ARCEP dans l'indicateur connectivité.

Clé composite :
- arrondissement temporel : "{arr:02d}_{annee}"
- quartier temporel       : "{code_quartier}_{annee}"
"""

import os
import sys
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ==========================================================================
# CHEMINS & CONFIG
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

# .env ancré sur la racine projet (indépendant du répertoire de lancement)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

SILVER_BASE = os.path.join(ROOT_DIR, "silver", "indicateur5")
PG_URL = os.getenv("PG_URL")

SURFACE_REF = 60  # m² — bien type pour le coût d'achat dérivé


def get_latest_date(base):
    """Dernier sous-dossier au format date AAAA-MM-JJ (ignore les autres dossiers)."""
    import re
    if not os.path.isdir(base):
        return None
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    dates = sorted([d for d in os.listdir(base)
                    if pat.match(d) and os.path.isdir(os.path.join(base, d))],
                   reverse=True)
    return dates[0] if dates else None


if len(sys.argv) > 1:
    date_str = sys.argv[1]
else:
    date_str = get_latest_date(SILVER_BASE) or datetime.now().strftime("%Y-%m-%d")

print(f"=== GOLD (IND5) — Accessibilite logement — date silver : {date_str} ===")

GOLD_DIR = os.path.join(ROOT_DIR, "gold", "indicateur5", date_str)
os.makedirs(GOLD_DIR, exist_ok=True)


def resolve_silver(filename):
    """Cherche un parquet Silver : a plat dans SILVER_BASE, sinon sous-dossier date."""
    flat = os.path.join(SILVER_BASE, filename)
    if os.path.isfile(flat):
        return flat
    dated = os.path.join(SILVER_BASE, date_str, filename)
    if os.path.isfile(dated):
        return dated
    raise FileNotFoundError(f"Silver introuvable : {filename} (ni a plat ni dans {date_str})")


# ==========================================================================
# FONCTIONS COMMUNES
# ==========================================================================
def normalize(series):
    """Min-max -> [0,1]. Constante -> 0.5."""
    s = pd.to_numeric(series, errors="coerce")
    min_v, max_v = s.min(), s.max()
    if pd.isna(min_v) or max_v == min_v:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - min_v) / (max_v - min_v)


def exporter(df_gold, table_name, pk_cols, parquet_path, engine):
    df_gold.to_parquet(parquet_path, index=False)
    print(f"OK Parquet : {parquet_path}")
    if engine is None:
        print(f"-- PostgreSQL non initialise -- {table_name} non exporte.")
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(text(f"DROP TABLE IF EXISTS gold.{table_name} CASCADE;"))
            conn.commit()
        df_gold.to_sql(table_name, engine, if_exists="replace", index=False, schema="gold")
        pk = ", ".join(pk_cols)
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE gold.{table_name} ADD PRIMARY KEY ({pk})"))
            conn.commit()
        print(f"OK PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)")
    except Exception as e:
        print(f"XX PostgreSQL indisponible pour {table_name} : {e}")


def calculer_score(df, niveau="arrondissement"):
    """Sous-scores normalises + score d'accessibilite + categorie.

    niveau='arrondissement' : inclut score_revenu (FILOSOFI natif)
    niveau='quartier'       : exclut score_revenu (donnee non native -> biais)
    """
    df = df.copy()

    df["score_prix"] = 1 - normalize(df["prix_m2_median"])
    df["score_social"] = normalize(df["nb_logements"])

    if niveau == "arrondissement":
        df["capacite_achat"] = (df["revenu_median"] / df["prix_m2_median"]).round(3)
        df["score_revenu"] = normalize(df["capacite_achat"])
        df["score_accessibilite"] = (
            df["score_prix"] * 0.40
            + df["score_social"] * 0.25
            + df["score_revenu"] * 0.35
        ).round(4)
    else:
        df["score_accessibilite"] = (
            df["score_prix"] * 0.60
            + df["score_social"] * 0.40
        ).round(4)

    df["score_accessibilite_100"] = (df["score_accessibilite"] * 100).round(1)
    df["categorie"] = pd.cut(
        df["score_accessibilite"],
        bins=[0, 0.33, 0.66, 1.0],
        labels=["Peu accessible", "Accessible", "Tres accessible"],
        include_lowest=True,
    )
    return df


def classer_par_annee(df):
    """Rang d'accessibilite au sein de chaque annee (1 = plus accessible)."""
    df = df.copy()
    df["rang"] = (
        df.groupby("annee")["score_accessibilite"]
        .rank(ascending=False, method="first")
    )
    df["rang"] = df["rang"].astype("Int64")
    return df


# ==========================================================================
# CHARGEMENT SILVER
# ==========================================================================
print("--- CHARGEMENT DES DONNEES SILVER ---")

df_dvf_arr = pd.read_parquet(resolve_silver("dvf_silver.parquet"))
df_ls_arr = pd.read_parquet(resolve_silver("logements_sociaux_silver.parquet"))
df_filo = pd.read_parquet(resolve_silver("filosofi_silver.parquet"))

df_dvf_qu = pd.read_parquet(resolve_silver("dvf_silver_quartier.parquet"))
df_ls_qu = pd.read_parquet(resolve_silver("logements_sociaux_silver_quartier.parquet"))

print(f"DVF arr/quartier : {df_dvf_arr.shape} / {df_dvf_qu.shape}")
print(f"LS  arr/quartier : {df_ls_arr.shape} / {df_ls_qu.shape}")
print(f"FILOSOFI (arr)   : {df_filo.shape}")

for d in (df_dvf_arr, df_ls_arr, df_filo, df_dvf_qu, df_ls_qu):
    if "cle" in d.columns:
        d.drop(columns=["cle"], inplace=True)
df_filo = df_filo.rename(columns={"millesime": "filosofi_millesime"})

try:
    engine = create_engine(PG_URL) if PG_URL else None
except Exception as e:
    engine = None
    print(f"-- PostgreSQL non initialise : {e}")


# ==========================================================================
# BLOC 1 — ARRONDISSEMENT x ANNEE (avec revenus)
# ==========================================================================
print("\n--- GOLD ARRONDISSEMENT ---")

df_arr = df_dvf_arr.merge(df_ls_arr, on=["arrondissement", "annee"], how="outer")
df_arr = df_arr.merge(df_filo, on="arrondissement", how="left")  # FILOSOFI broadcast

df_arr = df_arr[df_arr["arrondissement"].between(1, 20)]
df_arr = df_arr.dropna(subset=["arrondissement", "annee"])
df_arr["arrondissement"] = df_arr["arrondissement"].astype(int)
df_arr["annee"] = df_arr["annee"].astype(int)

count_cols = ["nb_ventes", "nb_logements", "nb_plai", "nb_plus",
              "nb_plus_cd", "nb_pls", "nb_programmes"]
for c in count_cols:
    if c in df_arr.columns:
        df_arr[c] = df_arr[c].fillna(0).astype(int)

df_arr["prix_bien_60m2"] = (df_arr["prix_m2_median"] * SURFACE_REF).round(0)
df_arr["taux_effort_achat"] = (df_arr["prix_bien_60m2"] / df_arr["revenu_median"]).round(1)

df_arr = calculer_score(df_arr, niveau="arrondissement")
df_arr = classer_par_annee(df_arr)

df_arr["cle"] = df_arr["arrondissement"].map("{:02d}".format) + "_" + df_arr["annee"].astype(str)

assert df_arr["cle"].is_unique, "cles arrondissement non uniques"
assert df_arr["arrondissement"].between(1, 20).all()
scored = df_arr["score_accessibilite"].dropna()
assert scored.between(0, 1).all(), "score arrondissement hors [0,1]"

front = ["cle", "arrondissement", "annee"]
cols_arr = front + [c for c in df_arr.columns if c not in front]
df_arr_gold = df_arr[cols_arr].sort_values(["annee", "rang"]).reset_index(drop=True)

print(f"Lignes : {len(df_arr_gold)} | Periode : {df_arr_gold['annee'].min()}-{df_arr_gold['annee'].max()}")

exporter(
    df_arr_gold,
    table_name="accessibilite_logement",
    pk_cols=["cle"],
    parquet_path=os.path.join(GOLD_DIR, "accessibilite_logement_gold.parquet"),
    engine=engine,
)


# ==========================================================================
# BLOC 2 — QUARTIER x ANNEE (sans revenus)
# ==========================================================================
print("\n--- GOLD QUARTIER ---")

df_qu = df_dvf_qu.merge(
    df_ls_qu, on=["code_quartier", "annee"], how="outer", suffixes=("", "_ls"),
)

for base in ["nom_quartier", "arrondissement"]:
    alt = f"{base}_ls"
    if alt in df_qu.columns:
        df_qu[base] = df_qu[base].fillna(df_qu[alt])
        df_qu.drop(columns=[alt], inplace=True)

df_qu = df_qu.dropna(subset=["code_quartier", "annee"])
df_qu["code_quartier"] = df_qu["code_quartier"].astype(int)
df_qu["annee"] = df_qu["annee"].astype(int)

for c in count_cols:
    if c in df_qu.columns:
        df_qu[c] = df_qu[c].fillna(0).astype(int)

df_qu = calculer_score(df_qu, niveau="quartier")
df_qu = classer_par_annee(df_qu)

df_qu["cle"] = df_qu["code_quartier"].astype(str) + "_" + df_qu["annee"].astype(str)

assert df_qu["cle"].is_unique, "cles quartier non uniques"
scored_qu = df_qu["score_accessibilite"].dropna()
assert scored_qu.between(0, 1).all(), "score quartier hors [0,1]"

front_qu = ["cle", "code_quartier", "nom_quartier", "arrondissement", "annee"]
cols_qu = front_qu + [c for c in df_qu.columns if c not in front_qu]
df_qu_gold = df_qu[[c for c in cols_qu if c in df_qu.columns]].sort_values(
    ["annee", "rang"]
).reset_index(drop=True)

print(f"Lignes : {len(df_qu_gold)} | Quartiers : {df_qu_gold['code_quartier'].nunique()}")

exporter(
    df_qu_gold,
    table_name="accessibilite_logement_quartier",
    pk_cols=["cle"],
    parquet_path=os.path.join(GOLD_DIR, "accessibilite_logement_quartier_gold.parquet"),
    engine=engine,
)

print("\n=== GOLD accessibilite logement OK ===")
