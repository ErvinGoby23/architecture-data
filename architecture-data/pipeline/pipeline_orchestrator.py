"""
pipeline_orchestrator.py — Orchestrateur Centralisé (Batch Quotidien - Pipeline Parallèle par Indicateur)
Urban Data Explorer · Bronze -> Silver -> Gold
Chaque indicateur est une chaîne indépendante qui s'exécute en parallèle.
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from prefect import flow, task, get_run_logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

PG_URL         = os.getenv("PG_URL",         "postgresql://postgres:test123@localhost:5432/postgres")
PG_URL_REPLICA = os.getenv("PG_URL_REPLICA", "postgresql://postgres:test123@localhost:5433/postgres")

LOCK_DIR = os.path.join(ROOT_DIR, "pipeline", "locks")

def run_script(path: str, arg: str = None) -> float:
    start = time.time()
    cmd = [sys.executable, path]
    if arg:
        cmd.append(arg)
    subprocess.run(cmd, check=True, cwd=os.path.dirname(path))
    return round(time.time() - start, 1)

def file_size_mb(path: str) -> float:
    return round(os.path.getsize(path) / 1_000_000, 2) if os.path.exists(path) else 0

def folder_size_mb(path: str) -> float:
    if not os.path.exists(path):
        return 0
    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(path)
        for f in files if f.endswith('.parquet')
    )
    return round(total / 1_000_000, 2)

def check_pg_primary(logger) -> bool:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(PG_URL, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL primary (5432) : disponible")
        return True
    except Exception:
        logger.warning("PostgreSQL primary (5432) : indisponible — pipeline en mode Parquet uniquement")
        return False

def check_pg_replica(logger) -> bool:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(PG_URL_REPLICA, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL replica  (5433) : disponible et synchronise")
        return True
    except Exception:
        logger.warning("PostgreSQL replica  (5433) : indisponible")
        return False


# ==========================================================================
# INDICATEUR 1 — Mobilité
# Bronze fetch → Silver (3 scripts en //) → Fusion → Gold
# ==========================================================================

@task(name="Bronze - Fetch stationnement", retries=2, retry_delay_seconds=60)
def run_bronze_stationnement(date_str: str):
    logger = get_run_logger()
    script = os.path.join(BASE_DIR, "fetch_stationnement.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "indicateur-Score-accessibilité-mobilité",
                              date_str, "stationnement-voie-publique-emplacements.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour deja present ({size_mb} MB)")
    else:
        logger.info(f"Fetch stationnement OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}

@task(name="Silver - Arrets lignes", retries=1)
def run_silver_arrets(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_arrets_lignes.py"), date_str)
    logger.info(f"Silver arrets OK en {duration}s")
    return duration

@task(name="Silver - Bornes taxi", retries=1)
def run_silver_taxi(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_bornes_taxi.py"), date_str)
    logger.info(f"Silver taxi OK en {duration}s")
    return duration

@task(name="Silver - Stationnement", retries=1)
def run_silver_stationnement(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_stationnement.py"), date_str)
    logger.info(f"Silver stationnement OK en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 1", retries=1)
def run_silver_fusion_ind1(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_fusion.py"), date_str)
        logger.info(f"Fusion ind1 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind1 — PostgreSQL indisponible : {e}")
        return None

@task(name="Gold - Score mobilite", retries=1)
def run_gold_mobilite(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "gold", "indicateur1", "gold_score_mobilite.py"), date_str)
        logger.info(f"Gold mobilite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold mobilite — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# INDICATEUR 2 — Connectivité
# Bronze fetch → Silver (2 scripts en //) → Fusion → Gold
# ==========================================================================

@task(name="Bronze - Fetch antennes relais", retries=2, retry_delay_seconds=60)
def run_bronze_antennes(date_str: str):
    logger = get_run_logger()
    script = os.path.join(BASE_DIR, "fetch_antennes_relais.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "Score-de-connectivite",
                              date_str, "antennes-relais.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour deja present ({size_mb} MB)")
    else:
        logger.info(f"Fetch antennes OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}

@task(name="Silver - Antennes relais", retries=1)
def run_silver_antennes_s(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_antennes_silver.py"), date_str)
    logger.info(f"Silver antennes OK en {duration}s")
    return duration

@task(name="Silver - Fibre", retries=1)
def run_silver_fibre(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_fibre_silver.py"), date_str)
    logger.info(f"Silver fibre OK en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 2", retries=1)
def run_silver_fusion_ind2(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur2", "silver_connectivite_fusion.py"), date_str)
        logger.info(f"Fusion ind2 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind2 — PostgreSQL indisponible : {e}")
        return None

@task(name="Gold - Score connectivite", retries=1)
def run_gold_connectivite(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "gold", "indicateur2", "gold_score_connectivite.py"), date_str)
        logger.info(f"Gold connectivite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold connectivite — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# INDICATEUR 3 — Vivabilité
# Pas de bronze (fichiers statiques) → Silver (5 scripts en //) → Fusion → Gold
# ==========================================================================


@task(name="Silver - Criminalite", retries=1)
def run_silver_criminalite(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur3", "silver_criminalite.py"), date_str)
    logger.info(f"Silver criminalite OK en {duration}s")
    return duration

@task(name="Silver - Espaces verts", retries=1)
def run_silver_espaces_verts(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur3", "silver_espaces_verts.py"), date_str)
    logger.info(f"Silver espaces verts OK en {duration}s")
    return duration

@task(name="Silver - Proprete", retries=1)
def run_silver_proprete(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur3", "silver_proprete.py"), date_str)
    logger.info(f"Silver proprete OK en {duration}s")
    return duration

@task(name="Silver - NO2", retries=1)
def run_silver_no2(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur3", "silver_NO2.py"), date_str)
    logger.info(f"Silver NO2 OK en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 3", retries=1)
def run_silver_fusion_ind3(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur3", "silver_fusion_vivabilite.py"), date_str)
        logger.info(f"Fusion ind3 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind3 — PostgreSQL/MongoDB indisponible : {e}")
        return None

@task(name="Gold - Score vivabilite", retries=1)
def run_gold_vivabilite(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "gold", "indicateur3", "gold_score_vivabilite.py"), date_str)
        logger.info(f"Gold vivabilite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold vivabilite — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# INDICATEUR 4 — Services du quotidien
# Pas de bronze → Silver (3 scripts en //) → Fusion → Gold
# ==========================================================================

@task(name="Silver - Commerces", retries=1)
def run_silver_commerces(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_comerce.py"), date_str)
    logger.info(f"Silver commerces OK en {duration}s")
    return duration

@task(name="Silver - Commissariats", retries=1)
def run_silver_commissariats(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_commissariats.py"), date_str)
    logger.info(f"Silver commissariats OK en {duration}s")
    return duration

@task(name="Silver - Ecoles elementaires", retries=1)
def run_silver_ecoles(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_ecoles_elementaires.py"), date_str)
    logger.info(f"Silver ecoles OK en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 4", retries=1)
def run_silver_fusion_ind4(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_fusion_services.py"), date_str)
        logger.info(f"Fusion ind4 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind4 — PostgreSQL indisponible : {e}")
        return None

@task(name="Gold - Score services", retries=1)
def run_gold_services(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "gold", "indicateur4", "gold_score_services.py"), date_str)
        logger.info(f"Gold services OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold services — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# INDICATEUR 5 — Logement
# Pas de bronze → Silver (3 scripts en //) → Fusion → Gold
# ==========================================================================

@task(name="Silver - DVF", retries=1)
def run_silver_dvf(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur5", "silver_dvf.py"), date_str)
    logger.info(f"Silver DVF OK en {duration}s")
    return duration

@task(name="Silver - Logements sociaux", retries=1)
def run_silver_logements_sociaux(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur5", "silver_logements_sociaux.py"), date_str)
    logger.info(f"Silver logements sociaux OK en {duration}s")
    return duration

@task(name="Silver - FILOSOFI", retries=1)
def run_silver_filosofi(date_str: str):
    logger = get_run_logger()
    duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur5", "silver_filosofi.py"), date_str)
    logger.info(f"Silver FILOSOFI OK en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 5", retries=1)
def run_silver_fusion_ind5(date_str: str):
    logger = get_run_logger()
    try:
        duration = run_script(os.path.join(ROOT_DIR, "silver", "indicateur5", "fusion_logement.py"), date_str)
        logger.info(f"Fusion ind5 OK en {duration}s")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind5 — erreur : {e}")
        return None

@task(name="Gold - Score accessibilite logement", retries=1)
def run_gold_accessibilite(date_str: str):
    logger = get_run_logger()
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    try:
        duration = run_script(os.path.join(ROOT_DIR, "gold", "indicateur5", "gold_score_accessibilite.py"), date_str)
        logger.info(f"Gold accessibilite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold accessibilite — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# LOAD TEST
# ==========================================================================

@task(name="Load Test - PostgreSQL Silver + Gold", retries=0)
def run_load_test(date_str: str):
    logger = get_run_logger()
    try:
        duration = run_script(os.path.join(ROOT_DIR, "test_deperfomance", "load_test_postgresql.py"), date_str)
        logger.info(f"Load test OK en {duration}s")
        return duration
    except Exception as e:
        logger.warning(f"Load test ignore — PostgreSQL indisponible : {e}")
        return None


# ==========================================================================
# CHAÎNES PAR INDICATEUR (sous-flows)
# Chaque chaîne est autonome : bronze → silver → fusion → gold
# ==========================================================================

@task(name="Pipeline - Indicateur 1 Mobilite", retries=0)
def chain_ind1(date_str: str):
    """Bronze fetch → Silver // → Fusion → Gold"""
    logger = get_run_logger()
    logger.info("=== IND1 Mobilite : debut ===")

    perf = run_bronze_stationnement(date_str)

    f_arrets = run_silver_arrets.submit(date_str)
    f_taxi   = run_silver_taxi.submit(date_str)
    f_stat   = run_silver_stationnement.submit(date_str)
    f_arrets.result(); f_taxi.result(); f_stat.result()

    run_silver_fusion_ind1(date_str)
    run_gold_mobilite(date_str)
    logger.info("=== IND1 Mobilite : OK ===")
    return perf


@task(name="Pipeline - Indicateur 2 Connectivite", retries=0)
def chain_ind2(date_str: str):
    """Bronze fetch → Silver // → Fusion → Gold"""
    logger = get_run_logger()
    logger.info("=== IND2 Connectivite : debut ===")

    perf = run_bronze_antennes(date_str)

    f_ant   = run_silver_antennes_s.submit(date_str)
    f_fibre = run_silver_fibre.submit(date_str)
    f_ant.result(); f_fibre.result()

    run_silver_fusion_ind2(date_str)
    run_gold_connectivite(date_str)
    logger.info("=== IND2 Connectivite : OK ===")
    return perf


@task(name="Pipeline - Indicateur 3 Vivabilite", retries=0)
def chain_ind3(date_str: str):
    """Pas de bronze (fichiers statiques) → Silver // → Fusion → Gold"""
    logger = get_run_logger()
    logger.info("=== IND3 Vivabilite : debut ===")

    f_crim  = run_silver_criminalite.submit(date_str)
    f_ev    = run_silver_espaces_verts.submit(date_str)
    f_prop  = run_silver_proprete.submit(date_str)
    f_no2   = run_silver_no2.submit(date_str)
    f_crim.result(); f_ev.result(); f_prop.result(); f_no2.result()

    run_silver_fusion_ind3(date_str)
    run_gold_vivabilite(date_str)
    logger.info("=== IND3 Vivabilite : OK ===")


@task(name="Pipeline - Indicateur 4 Services", retries=0)
def chain_ind4(date_str: str):
    """Pas de bronze → Silver // → Fusion → Gold"""
    logger = get_run_logger()
    logger.info("=== IND4 Services : debut ===")

    f_comm  = run_silver_commerces.submit(date_str)
    f_commi = run_silver_commissariats.submit(date_str)
    f_eco   = run_silver_ecoles.submit(date_str)
    f_comm.result(); f_commi.result(); f_eco.result()

    run_silver_fusion_ind4(date_str)
    run_gold_services(date_str)
    logger.info("=== IND4 Services : OK ===")


@task(name="Pipeline - Indicateur 5 Logement", retries=0)
def chain_ind5(date_str: str):
    """Pas de bronze → Silver // → Fusion → Gold"""
    logger = get_run_logger()
    logger.info("=== IND5 Logement : debut ===")

    f_dvf  = run_silver_dvf.submit(date_str)
    f_ls   = run_silver_logements_sociaux.submit(date_str)
    f_filo = run_silver_filosofi.submit(date_str)
    f_dvf.result(); f_ls.result(); f_filo.result()

    run_silver_fusion_ind5(date_str)
    run_gold_accessibilite(date_str)
    logger.info("=== IND5 Logement : OK ===")


# ==========================================================================
# FLOW PRINCIPAL
# ==========================================================================

@flow(name="Urban Data Explorer — Main Daily Batch")
def main_pipeline():
    logger = get_run_logger()
    current_date = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_file = os.path.join(LOCK_DIR, f"{current_date}.lock")
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        logger.warning(f"Run deja effectue (ou en cours) pour {current_date} — annulation")
        return

    try:
        global_start = time.time()
        logger.info(f"=== DEMARRAGE DU BATCH — {current_date} ===")

        primary_ok = check_pg_primary(logger)
        replica_ok = check_pg_replica(logger)

        if primary_ok and replica_ok:
            logger.info("Architecture HA : primary (5432) + replica (5433) — WAL streaming actif")
        elif primary_ok:
            logger.warning("Architecture degradee : primary seul disponible")
        else:
            logger.warning("PostgreSQL indisponible — pipeline en mode Parquet uniquement")

        # ── Les 5 chaînes tournent en parallèle ─────────────────────────
        # Chaque chaîne gère son propre bronze → silver → fusion → gold
        f1 = chain_ind1.submit(current_date)
        f2 = chain_ind2.submit(current_date)
        f3 = chain_ind3.submit(current_date)
        f4 = chain_ind4.submit(current_date)
        f5 = chain_ind5.submit(current_date)

        perf_stat = f1.result()
        perf_ant  = f2.result()
        f3.result()
        f4.result()
        f5.result()

        logger.info("Toutes les chaines indicateur OK")

        # ── LOAD TEST ────────────────────────────────────────────────────
        run_load_test(current_date)

        # ── RAPPORT DE PERFORMANCE (C2.4) ────────────────────────────────
        total_duration = round(time.time() - global_start, 1)
        bronze_skipped = perf_stat.get("skipped", False) or perf_ant.get("skipped", False)

        vol_bronze_stat = perf_stat["size_mb"]
        vol_bronze_ant  = perf_ant["size_mb"]
        vol_bronze      = round(vol_bronze_stat + vol_bronze_ant, 2)

        vol_silver_ind1 = folder_size_mb(os.path.join(ROOT_DIR, "silver", "indicateur1", "nettoyage-indicateur1", current_date))
        vol_silver_ind2 = folder_size_mb(os.path.join(ROOT_DIR, "silver", "indicateur2", "nettoyage-indicateur2", current_date))
        vol_silver_ind3 = folder_size_mb(os.path.join(ROOT_DIR, "silver", "indicateur3", "nettoyage-indicateur3", current_date))
        vol_silver_ind4 = folder_size_mb(os.path.join(ROOT_DIR, "silver", "indicateur4", "nettoyage-indicateur4", current_date))
        vol_silver_ind5 = folder_size_mb(os.path.join(ROOT_DIR, "silver", "indicateur5", current_date))
        vol_silver      = round(vol_silver_ind1 + vol_silver_ind2 + vol_silver_ind3 + vol_silver_ind4 + vol_silver_ind5, 2)

        vol_gold_ind1 = folder_size_mb(os.path.join(ROOT_DIR, "gold", "indicateur1", current_date))
        vol_gold_ind2 = folder_size_mb(os.path.join(ROOT_DIR, "gold", "indicateur2", current_date))
        vol_gold_ind3 = folder_size_mb(os.path.join(ROOT_DIR, "gold", "indicateur3", current_date))
        vol_gold_ind4 = folder_size_mb(os.path.join(ROOT_DIR, "gold", "indicateur4", current_date))
        vol_gold_ind5 = folder_size_mb(os.path.join(ROOT_DIR, "gold", "indicateur5", current_date))
        vol_gold      = round(vol_gold_ind1 + vol_gold_ind2 + vol_gold_ind3 + vol_gold_ind4 + vol_gold_ind5, 2)

        total_volume = round(vol_bronze + vol_silver + vol_gold, 2)
        debit_mbs    = round(total_volume / total_duration, 2) if total_duration > 0 else 0

        logger.info("=== RAPPORT DE PERFORMANCE (C2.4) ===")
        logger.info(f"Temps total d'execution  : {total_duration}s")
        logger.info(f"--- Bronze (APIs) ---")
        logger.info(f"  Stationnement          : {vol_bronze_stat} MB")
        logger.info(f"  Antennes relais        : {vol_bronze_ant} MB")
        logger.info(f"  Total Bronze           : {vol_bronze} MB")
        logger.info(f"--- Silver (Parquet) ---")
        logger.info(f"  Indicateur 1 Mobilite     : {vol_silver_ind1} MB")
        logger.info(f"  Indicateur 2 Connectivite : {vol_silver_ind2} MB")
        logger.info(f"  Indicateur 3 Vivabilite   : {vol_silver_ind3} MB")
        logger.info(f"  Indicateur 4 Services     : {vol_silver_ind4} MB")
        logger.info(f"  Indicateur 5 Logement     : {vol_silver_ind5} MB")
        logger.info(f"  Total Silver              : {vol_silver} MB")
        logger.info(f"--- Gold (Parquet) ---")
        logger.info(f"  Indicateur 1 Mobilite     : {vol_gold_ind1} MB")
        logger.info(f"  Indicateur 2 Connectivite : {vol_gold_ind2} MB")
        logger.info(f"  Indicateur 3 Vivabilite   : {vol_gold_ind3} MB")
        logger.info(f"  Indicateur 4 Services     : {vol_gold_ind4} MB")
        logger.info(f"  Indicateur 5 Logement     : {vol_gold_ind5} MB")
        logger.info(f"  Total Gold                : {vol_gold} MB")
        logger.info(f"--- Synthese ---")
        logger.info(f"Volume total pipeline    : {total_volume} MB")
        logger.info(f"Debit moyen              : {debit_mbs} MB/s")
        logger.info(f"Comportement ce jour     : {'SKIP FETCH' if bronze_skipped else 'FETCH OK'}")
        logger.info(f"PostgreSQL primary (5432) : {'OK' if primary_ok else 'INDISPONIBLE'}")
        logger.info(f"PostgreSQL replica  (5433) : {'OK - WAL streaming actif' if replica_ok else 'INDISPONIBLE'}")
        logger.info("Load test                : Resultats dans test_deperfomance/results/")
        logger.info("=====================================")

    except Exception:
        if os.path.exists(lock_file):
            os.remove(lock_file)
        raise


if __name__ == "__main__":
    main_pipeline.serve(
        name="daily-urban-explorer-sync",
        cron="0 3 * * *",
        pause_on_shutdown=True,
    )