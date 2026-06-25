"""
Silver — DVF géolocalisées (transactions immobilières)
======================================================
Source Bronze : transactions brutes (1 ligne = 1 lot d'une mutation)

DEUX sorties (modèle deux-blocs, cf. gold_score_connectivite) :
  1. ARRONDISSEMENT × année  -> cle = "{arr:02d}_{annee}"
  2. QUARTIER × année        -> cle = "{code_quartier}_{annee}"
     (jointure spatiale point lon/lat -> quartier via quartiers.csv)

Indicateurs : prix_m2_median, prix_m2_moyen, nb_ventes, surface_mediane,
              valeur_fonciere_mediane 
"""

import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJET = HERE.parents[1]
BRONZE = PROJET / "brute" / "Indicateurs de logement" / "dvf2.parquet"
QUARTIERS_CSV = PROJET / "brute" / "indicateur-Score-accessibilité-mobilité" / "quartiers.csv"

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")

SILVER_DIR = HERE / "nettoyage-indicateur5" / date_str
SILVER_OUT = SILVER_DIR / "dvf_silver.parquet"
SILVER_OUT_QU = SILVER_DIR / "dvf_silver_quartier.parquet"

PRIX_M2_MIN, PRIX_M2_MAX = 2_000, 40_000


def load_bronze(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier Bronze introuvable : {path}\n"
            f"Racine projet détectée : {PROJET}"
        )
    colonnes_utiles = ['id_mutation', 'date_mutation', 'valeur_fonciere', 'code_commune',
                       'type_local', 'nature_mutation', 'surface_reelle_bati',
                       'longitude', 'latitude']
    df = pd.read_parquet(path, columns=colonnes_utiles)
    df.columns = df.columns.str.strip()
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    num_cols = ["valeur_fonciere", "surface_reelle_bati", "longitude", "latitude"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(
                df[c].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )
    df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")
    df["annee"] = df["date_mutation"].dt.year
    df["arrondissement"] = df["code_commune"].astype(str).str[-2:]
    df["arrondissement"] = pd.to_numeric(df["arrondissement"], errors="coerce")
    df = df.drop_duplicates()
    return df


def filtre_metier(df: pd.DataFrame) -> pd.DataFrame:
    appt = df[
        (df["type_local"] == "Appartement")
        & (df["nature_mutation"] == "Vente")
        & (df["valeur_fonciere"] > 0)
        & (df["surface_reelle_bati"] > 0)
    ].copy()

    appt = appt.dropna(subset=["arrondissement", "annee"])
    appt["arrondissement"] = appt["arrondissement"].astype(int)
    appt["annee"] = appt["annee"].astype(int)
    appt = appt[appt["arrondissement"].between(1, 20)]

    grp = appt.groupby("id_mutation")
    mut = grp.agg(
        valeur_fonciere=("valeur_fonciere", "first"),
        surface_reelle_bati=("surface_reelle_bati", "sum"),
        arrondissement=("arrondissement", "first"),
        annee=("annee", "first"),
        longitude=("longitude", "first"),
        latitude=("latitude", "first"),
    ).reset_index()

    mut["prix_m2"] = mut["valeur_fonciere"] / mut["surface_reelle_bati"]
    mut = mut[mut["prix_m2"].between(PRIX_M2_MIN, PRIX_M2_MAX)]
    return mut


def _agg(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    g = (
        df.groupby(group_cols)
        .agg(
            prix_m2_median=("prix_m2", "median"),
            prix_m2_moyen=("prix_m2", "mean"),
            nb_ventes=("prix_m2", "size"),
            surface_mediane=("surface_reelle_bati", "median"),
            valeur_fonciere_mediane=("valeur_fonciere", "median"),
        )
        .reset_index()
    )
    g["prix_m2_median"] = g["prix_m2_median"].round(0)
    g["prix_m2_moyen"] = g["prix_m2_moyen"].round(0)
    g["surface_mediane"] = g["surface_mediane"].round(1)
    g["valeur_fonciere_mediane"] = g["valeur_fonciere_mediane"].round(0)
    return g


def aggregate_arr(appt: pd.DataFrame) -> pd.DataFrame:
    g = _agg(appt, ["arrondissement", "annee"])
    g["cle"] = (g["arrondissement"].map("{:02d}".format) + "_" + g["annee"].astype(str))
    cols = ["cle", "arrondissement", "annee", "prix_m2_median", "prix_m2_moyen",
            "nb_ventes", "surface_mediane", "valeur_fonciere_mediane"]
    return g[cols].sort_values(["arrondissement", "annee"]).reset_index(drop=True)


def _charger_quartiers_gdf():
    import json
    import geopandas as gpd
    from shapely.geometry import shape

    df_qu = pd.read_csv(QUARTIERS_CSV, sep=";")
    df_qu.columns = df_qu.columns.str.strip()

    geo_col = next((c for c in df_qu.columns
                    if "geometry" in c.lower() and "x y" not in c.lower()), None)
    if geo_col is None:
        geo_col = next((c for c in df_qu.columns if "geom" in c.lower()), None)

    def parse_geom(s):
        try:
            return shape(json.loads(s)) if pd.notna(s) else None
        except Exception:
            return None

    df_qu["geometry"] = df_qu[geo_col].apply(parse_geom)
    df_qu = df_qu.dropna(subset=["geometry"])
    gdf_qu = gpd.GeoDataFrame(df_qu, geometry="geometry", crs="EPSG:4326")
    cols = [c for c in ["C_QU", "L_QU", "geometry"] if c in gdf_qu.columns]
    return gdf_qu[cols]


def aggregate_quartier(appt: pd.DataFrame) -> pd.DataFrame:
    import geopandas as gpd

    gdf_qu = _charger_quartiers_gdf()

    pts = appt.dropna(subset=["longitude", "latitude"]).copy()
    gdf_pts = gpd.GeoDataFrame(
        pts,
        geometry=gpd.points_from_xy(pts["longitude"], pts["latitude"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(gdf_pts, gdf_qu, how="left", predicate="within")
    joined = joined.rename(columns={"C_QU": "code_quartier", "L_QU": "nom_quartier"})
    joined = joined.drop(columns=[c for c in joined.columns
                                  if c.startswith("index_right")], errors="ignore")

    joined["code_quartier"] = pd.to_numeric(joined["code_quartier"], errors="coerce")
    joined = joined.dropna(subset=["code_quartier", "annee"])
    joined["code_quartier"] = joined["code_quartier"].astype(int)

    g = _agg(joined, ["code_quartier", "annee"])
    ref = joined.drop_duplicates("code_quartier")[
        ["code_quartier", "nom_quartier", "arrondissement"]]
    g = g.merge(ref, on="code_quartier", how="left")
    g["cle"] = g["code_quartier"].astype(str) + "_" + g["annee"].astype(str)
    cols = ["cle", "code_quartier", "nom_quartier", "arrondissement", "annee",
            "prix_m2_median", "prix_m2_moyen", "nb_ventes",
            "surface_mediane", "valeur_fonciere_mediane"]
    return g[[c for c in cols if c in g.columns]].sort_values(
        ["code_quartier", "annee"]).reset_index(drop=True)


def prefiltre_paris(df: pd.DataFrame) -> pd.DataFrame:
    cc = df["code_commune"].astype("string")
    keep = (
        cc.str.startswith("751", na=False)
        & (df["type_local"] == "Appartement")
        & (df["nature_mutation"] == "Vente")
    )
    return df[keep].copy()


def main():
    df = load_bronze(BRONZE)
    print(f"[DVF] Bronze : {len(df):,} lignes")
    df = prefiltre_paris(df)
    print(f"[DVF] Après pré-filtre Paris/appartements : {len(df):,} lignes")
    df = clean(df)
    appt = filtre_metier(df)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    silver = aggregate_arr(appt)
    silver.to_parquet(SILVER_OUT, index=False)
    print(f"[DVF] Appartements valides : {len(appt):,}")
    print(f"[DVF] Silver ARR : {len(silver)} lignes -> {SILVER_OUT}")

    try:
        silver_qu = aggregate_quartier(appt)
        silver_qu.to_parquet(SILVER_OUT_QU, index=False)
        print(f"[DVF] Silver QUARTIER : {len(silver_qu)} lignes -> {SILVER_OUT_QU}")
        print(f"[DVF] Quartiers couverts : {silver_qu['code_quartier'].nunique()}")
    except Exception as e:
        print(f"[DVF] ⚠ Quartier ignoré (vérifie quartiers.csv) : {e}")

    print(silver.head(5).to_string(index=False))


if __name__ == "__main__":
    main()