"""
Silver — FILOSOFI (revenus & pauvreté) Paris
============================================
Source Bronze : format SDMX long (1 ligne = 1 mesure pour 1 géographie)
Sortie Silver : 1 ligne = 1 arrondissement
Clé composite : SOURCE NON TEMPORELLE (millésime unique 2021)
               ->  cle = "{arrondissement:02d}"   (PAS d'année dans la clé)

Indicateurs produits (indicateur obligatoire « accessibilité financière ») :
  - revenu_median        : MED_SL — médiane niveau de vie (€)
  - taux_pauvrete        : PR_MD60 — taux de pauvreté seuil 60% (%)
  - rapport_interdecile  : IR_D9_D1_SL — D9/D1 (inégalités)
  - decile1 / decile9    : D1_SL / D9_SL

Note : FILOSOFI ne descend pas sous l'arrondissement (ARM), et le millésime
est unique -> la clé composite est uniquement l'arrondissement.
On conserve `millesime` comme colonne (traçabilité) mais hors clé.
"""

from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJET = HERE.parents[1]
BRONZE = PROJET / "brute" / "Indicateurs de logement" / "DS_FILOSOFI_CC_data.csv"
SILVER_DIR = HERE
SILVER_OUT = SILVER_DIR / "filosofi_silver.parquet"

# mesures FILOSOFI -> noms Silver
MEASURE_MAP = {
    "MED_SL": "revenu_median",
    "PR_MD60": "taux_pauvrete",
    "IR_D9_D1_SL": "rapport_interdecile",
    "D1_SL": "decile1",
    "D9_SL": "decile9",
}


def load_bronze(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier Bronze introuvable : {path}\n"
            f"Vérifie l'arborescence. Racine projet détectée : {PROJET}"
        )
    df = pd.read_csv(path, sep=";", encoding="utf-8", engine="python")
    df.columns = df.columns.str.strip()
    return df


def extract_paris(df: pd.DataFrame) -> pd.DataFrame:
    """Niveau arrondissement (ARM), géo Paris 751XX."""
    paris = df[
        (df["GEO_OBJECT"] == "ARM")
        & (df["GEO"].astype(str).str.startswith("751"))
    ].copy()
    return paris


def pivot_wide(paris: pd.DataFrame) -> pd.DataFrame:
    """Long -> large : 1 ligne = 1 arrondissement."""
    piv = paris.pivot_table(
        index="GEO",
        columns="FILOSOFI_MEASURE",
        values="OBS_VALUE",
        aggfunc="first",
    )
    piv["arrondissement"] = piv.index.astype(str).str[-2:].astype(int)

    # garde + renomme les mesures d'intérêt présentes
    keep = {k: v for k, v in MEASURE_MAP.items() if k in piv.columns}
    out = piv[["arrondissement", *keep.keys()]].rename(columns=keep)

    # millésime (traçabilité, hors clé)
    out["millesime"] = pd.to_numeric(paris["TIME_PERIOD"].iloc[0], errors="coerce")

    out = out[out["arrondissement"].between(1, 20)]
    out = out.sort_values("arrondissement").reset_index(drop=True)

    # CLÉ COMPOSITE — source NON temporelle => arrondissement seul
    out["cle"] = out["arrondissement"].map("{:02d}".format)

    front = ["cle", "arrondissement", "millesime"]
    rest = [c for c in out.columns if c not in front]
    return out[front + rest]


def main():
    df = load_bronze(BRONZE)
    paris = extract_paris(df)
    silver = pivot_wide(paris)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(SILVER_OUT, index=False)

    print(f"[FILOSOFI] Bronze : {len(df):,} lignes (France)")
    print(f"[FILOSOFI] Paris ARM : {len(paris)} lignes")
    print(f"[FILOSOFI] Silver : {len(silver)} arrondissements")
    print(f"[FILOSOFI] Millésime : {int(silver['millesime'].iloc[0])}")
    print(f"[FILOSOFI] Écrit  : {SILVER_OUT}")
    print(silver.to_string(index=False))


if __name__ == "__main__":
    main()
