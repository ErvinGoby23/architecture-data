"""
Silver — Logements sociaux financés à Paris
===========================================
Source Bronze : 1 ligne = 1 programme de logements sociaux financés

DEUX sorties :
  1. ARRONDISSEMENT × année  -> cle = "{arr:02d}_{annee}"
  2. QUARTIER × année        -> cle = "{code_quartier}_{annee}"
     (jointure spatiale x_l93/y_l93 Lambert93 -> quartier via quartiers.csv)
"""

from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJET = HERE.parents[1]
BRONZE_NAME = "logements-sociaux-finances-a-paris.csv"
BRONZE = PROJET / "brute" / "Nouveau dossier" / BRONZE_NAME
QUARTIERS_CSV = PROJET / "brute" / "indicateur-Score-accessibilité-mobilité" / "quartiers.csv"
SILVER_DIR = HERE
SILVER_OUT = SILVER_DIR / "logements_sociaux_silver.parquet"
SILVER_OUT_QU = SILVER_DIR / "logements_sociaux_silver_quartier.parquet"

RENAME = {
    "Identifiant livraison": "id",
    "Adresse du programme": "adresse",
    "Code postal": "code_postal",
    "Ville": "ville",
    "Année du financement - agrément": "annee",
    "Bailleur social": "bailleur",
    "Nombre total de logements financés": "nb_logements",
    "Dont nombre de logements PLA I": "nb_plai",
    "Dont nombre de logements PLUS": "nb_plus",
    "Dont nombre de logements PLUS CD": "nb_plus_cd",
    "Dont nombre de logements PLS": "nb_pls",
    "Mode de réalisation": "mode_realisation",
    "Commentaires": "commentaires",
    "Arrondissement": "arrondissement",
    "Nature de programme": "nature_programme",
    "Coordonnée en X (L93)": "x_l93",
    "Coordonnée en Y (L93)": "y_l93",
}
NUM_COLS = ["annee", "nb_logements", "nb_plai", "nb_plus",
            "nb_plus_cd", "nb_pls", "arrondissement", "x_l93", "y_l93"]


def resolve_bronze() -> Path:
    if BRONZE.exists():
        return BRONZE
    matches = list((PROJET / "brute").rglob(BRONZE_NAME))
    if matches:
        print(f"[LS] Trouvé automatiquement : {matches[0]}")
        return matches[0]
    return BRONZE


def load_bronze(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier Bronze introuvable : {path}\nRacine projet détectée : {PROJET}")
    df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df.rename(columns=RENAME)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["arrondissement", "annee"])
    df["arrondissement"] = df["arrondissement"].astype(int)
    df["annee"] = df["annee"].astype(int)
    df = df[df["arrondissement"].between(1, 20)]
    return df


def _agg(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    g = (
        df.groupby(group_cols)
        .agg(
            nb_logements=("nb_logements", "sum"),
            nb_plai=("nb_plai", "sum"),
            nb_plus=("nb_plus", "sum"),
            nb_plus_cd=("nb_plus_cd", "sum"),
            nb_pls=("nb_pls", "sum"),
            nb_programmes=("nb_logements", "size"),
        )
        .reset_index()
    )
    int_cols = ["nb_logements", "nb_plai", "nb_plus", "nb_plus_cd", "nb_pls"]
    g[int_cols] = g[int_cols].fillna(0).round(0).astype(int)
    return g


def aggregate_arr(df: pd.DataFrame) -> pd.DataFrame:
    g = _agg(df, ["arrondissement", "annee"])
    g["cle"] = g["arrondissement"].map("{:02d}".format) + "_" + g["annee"].astype(str)
    cols = ["cle", "arrondissement", "annee", "nb_logements", "nb_plai",
            "nb_plus", "nb_plus_cd", "nb_pls", "nb_programmes"]
    return g[cols].sort_values(["arrondissement", "annee"]).reset_index(drop=True)


def _charger_quartiers_gdf():
    """Charge quartiers.csv (géométrie GeoJSON inline, schéma Open Data Paris)."""
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


def aggregate_quartier(df: pd.DataFrame) -> pd.DataFrame:
    """Jointure spatiale point (x_l93/y_l93 en Lambert-93) -> quartier, puis agrégation.

    Les coordonnées sont en Lambert-93 (EPSG:2154) : on construit les points dans
    ce CRS puis on reprojette en WGS84 avant la jointure avec le fond quartiers.
    """
    import geopandas as gpd

    gdf_qu = _charger_quartiers_gdf()

    pts = df.dropna(subset=["x_l93", "y_l93"]).copy()
    gdf_pts = gpd.GeoDataFrame(
        pts,
        geometry=gpd.points_from_xy(pts["x_l93"], pts["y_l93"]),
        crs="EPSG:2154",                      # Lambert-93
    ).to_crs("EPSG:4326")                       # -> WGS84 pour matcher les quartiers

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
            "nb_logements", "nb_plai", "nb_plus", "nb_plus_cd", "nb_pls", "nb_programmes"]
    return g[[c for c in cols if c in g.columns]].sort_values(
        ["code_quartier", "annee"]).reset_index(drop=True)


def main():
    df = load_bronze(resolve_bronze())
    df = clean(df)

    silver = aggregate_arr(df)
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(SILVER_OUT, index=False)
    print(f"[LS] Bronze nettoyé : {len(df):,} programmes")
    print(f"[LS] Silver ARR : {len(silver)} lignes -> {SILVER_OUT}")

    try:
        silver_qu = aggregate_quartier(df)
        silver_qu.to_parquet(SILVER_OUT_QU, index=False)
        print(f"[LS] Silver QUARTIER : {len(silver_qu)} lignes -> {SILVER_OUT_QU}")
        print(f"[LS] Quartiers couverts : {silver_qu['code_quartier'].nunique()}")
    except Exception as e:
        print(f"[LS] ⚠ Quartier ignoré (vérifie quartiers.csv / coords) : {e}")

    print(silver.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
