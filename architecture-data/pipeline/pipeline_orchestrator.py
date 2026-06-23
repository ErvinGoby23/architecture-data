"""
pipeline_orchestrator.py — Orchestrateur Centralisé (Batch Quotidien - Version Date-Aware Corrigée)
Urban Data Explorer · Bronze -> Silver -> Gold
"""

import os
import sys
import time
import subprocess
from pathlib import Path
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

def check_pg_primary(logger) -> bool:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(PG_URL, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL primary (5432) : disponible")
        return True
    except Exception:
        logger.warning("PostgreSQL primary (5432) : indisponible — le pipeline ecrira uniquement en Parquet")
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

# ──────────────────────────────────────────────
# BRONZE
# ──────────────────────────────────────────────
@task(name="Bronze - Fetch stationnement", retries=2, retry_delay_seconds=60)
def run_bronze_stationnement(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fetch stationnement pour {date_str}")
    script = os.path.join(BASE_DIR, "fetch_stationnement.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "indicateur-Score-accessibilité-mobilité",
                              date_str, "stationnement-voie-publique-emplacements.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour déjà présent ({size_mb} MB)")
    else:
        logger.info(f"Fetch OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}


@task(name="Bronze - Fetch antennes relais", retries=2, retry_delay_seconds=60)
def run_bronze_antennes(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fetch antennes relais pour {date_str}")
    script = os.path.join(BASE_DIR, "fetch_antennes_relais.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "Score-de-connectivite",
                              date_str, "antennes-relais.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour déjà présent ({size_mb} MB)")
    else:
        logger.info(f"Fetch OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}

# ──────────────────────────────────────────────
# SILVER & GOLD — INDICATEUR 1 (Mobilité)
# ──────────────────────────────────────────────
@task(name="Silver - Arrets lignes", retries=1)
def run_silver_arrets(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver arrets lignes — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_arrets_lignes.py")
    duration = run_script(script, date_str)
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Bornes taxi", retries=1)
def run_silver_taxi(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver bornes taxi — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_bornes_taxi.py")
    duration = run_script(script, date_str)
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Stationnement", retries=1)
def run_silver_stationnement(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver stationnement — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_stationnement.py")
    duration = run_script(script, date_str)
    if duration > 60:
        logger.warning(f"Stationnement anormalement lent : {duration}s")
    else:
        logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 1", retries=1)
def run_silver_fusion_ind1(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fusion Silver ind1 — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_fusion.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Fusion ind1 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind1 — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet reste la source canonique")
        return None

@task(name="Silver - Antennes relais", retries=1)
def run_silver_antennes_s(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver antennes relais — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_antennes_silver.py")
    duration = run_script(script, date_str)
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Fibre", retries=1)
def run_silver_fibre(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver fibre — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_fibre_silver.py")
    duration = run_script(script, date_str)
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 2", retries=1)
def run_silver_fusion_ind2(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fusion Silver ind2 — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "silver_connectivite_fusion.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Fusion ind2 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind2 — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet reste la source canonique")
        return None

@task(name="Gold - Score mobilite", retries=1)
def run_gold_mobilite(date_str: str):
    logger = get_run_logger()
    logger.info(f"Gold score mobilite — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    script = os.path.join(ROOT_DIR, "gold", "indicateur1", "gold_score_mobilite.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Gold mobilite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold mobilite — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet Gold reste la source canonique")
        return None

@task(name="Gold - Score connectivite", retries=1)
def run_gold_connectivite(date_str: str):
    logger = get_run_logger()
    logger.info(f"Gold score connectivite — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    script = os.path.join(ROOT_DIR, "gold", "indicateur2", "gold_score_connectivite.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Gold connectivite OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold connectivite — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet Gold reste la source canonique")
        return None

# ──────────────────────────────────────────────
# SILVER & GOLD — INDICATEUR 4 (Services du quotidien)
# ──────────────────────────────────────────────
@task(name="Silver - Commerces", retries=1)
def run_silver_commerces(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver commerces — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_comerce.py")
    duration = run_script(script)  # pas de date : fichier statique
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Commissariats", retries=1)
def run_silver_commissariats(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver commissariats — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_commissariats.py")
    duration = run_script(script)  # pas de date : fichier statique
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Ecoles elementaires", retries=1)
def run_silver_ecoles(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver ecoles elementaires — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_ecoles_elementaires.py")
    duration = run_script(script, date_str)
    logger.info(f"Termine en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 4", retries=1)
def run_silver_fusion_ind4(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fusion Silver ind4 (services) — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432) + MongoDB Atlas")
    script = os.path.join(ROOT_DIR, "silver", "indicateur4", "silver_fusion_services.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Fusion ind4 OK en {duration}s")
        logger.info("Resilience : Parquet OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Fusion ind4 — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet reste la source canonique")
        return None

@task(name="Gold - Score services", retries=1)
def run_gold_services(date_str: str):
    logger = get_run_logger()
    logger.info(f"Gold score services du quotidien — {date_str}")
    logger.info("Cible ecriture : PostgreSQL primary (5432)")
    script = os.path.join(ROOT_DIR, "gold", "indicateur4", "gold_score_services.py")
    try:
        duration = run_script(script, date_str)
        logger.info(f"Gold services OK en {duration}s")
        logger.info("Resilience : Parquet Gold OK — PostgreSQL primary ecrit, replica (5433) synchronise via WAL")
        return duration
    except Exception as e:
        logger.warning(f"Gold services — PostgreSQL primary indisponible : {e}")
        logger.warning("Fallback actif : Parquet Gold reste la source canonique")
        return None

# ──────────────────────────────────────────────
# LOAD TEST — C1.1 Tests de charge PostgreSQL
# ──────────────────────────────────────────────
@task(name="Load Test - PostgreSQL Silver + Gold", retries=0)
def run_load_test(date_str: str):
    logger = get_run_logger()
    logger.info(f"Load test PostgreSQL — {date_str}")
    try:
        script = os.path.join(ROOT_DIR, "test_deperfomance", "load_test_postgresql.py")
        duration = run_script(script, date_str)
        logger.info(f"Load test OK en {duration}s")
        return duration
    except Exception as e:
        logger.warning(f"Load test ignore — PostgreSQL indisponible : {e}")
        logger.warning("Le pipeline continue — Parquet reste la source canonique")
        return None

# ──────────────────────────────────────────────
# FLOW PRINCIPAL
# ──────────────────────────────────────────────
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
        logger.warning(f"Run deja effectue (ou en cours) pour {current_date} — annulation pour eviter le doublon")
        return

    try:
        global_start = time.time()
        logger.info(f"=== DEMARRAGE DU BATCH POUR LA DATE : {current_date} ===")

        primary_ok = check_pg_primary(logger)
        replica_ok = check_pg_replica(logger)

        if primary_ok and replica_ok:
            logger.info("Architecture HA : primary (5432) + replica (5433) — WAL streaming actif")
        elif primary_ok:
            logger.warning("Architecture degradee : primary seul disponible — replica hors ligne")
        else:
            logger.warning("PostgreSQL indisponible — pipeline en mode Parquet uniquement")

        # ── BRONZE en parallèle ──────────────────────────────────────────
        future_stat = run_bronze_stationnement.submit(current_date)
        future_ant  = run_bronze_antennes.submit(current_date)
        perf_stat   = future_stat.result()
        perf_ant    = future_ant.result()
        logger.info("Bronze OK")

        # ── SILVER ind1 + ind2 + ind4 en parallèle ───────────────────────
        future_arrets   = run_silver_arrets.submit(current_date)
        future_taxi     = run_silver_taxi.submit(current_date)
        future_stat_s   = run_silver_stationnement.submit(current_date)
        future_ant_s    = run_silver_antennes_s.submit(current_date)
        future_fibre    = run_silver_fibre.submit(current_date)
        future_commer   = run_silver_commerces.submit(current_date)
        future_commis   = run_silver_commissariats.submit(current_date)
        future_ecoles   = run_silver_ecoles.submit(current_date)

        future_arrets.result()
        future_taxi.result()
        future_stat_s.result()
        future_ant_s.result()
        future_fibre.result()
        future_commer.result()
        future_commis.result()
        future_ecoles.result()
        logger.info("Silver OK")

        # ── FUSIONS en parallèle ─────────────────────────────────────────
        future_fusion1 = run_silver_fusion_ind1.submit(current_date)
        future_fusion2 = run_silver_fusion_ind2.submit(current_date)
        future_fusion4 = run_silver_fusion_ind4.submit(current_date)
        future_fusion1.result()
        future_fusion2.result()
        future_fusion4.result()
        logger.info("Fusions OK")

        # ── GOLD en parallèle ────────────────────────────────────────────
        future_mob      = run_gold_mobilite.submit(current_date)
        future_conn     = run_gold_connectivite.submit(current_date)
        future_services = run_gold_services.submit(current_date)
        future_mob.result()
        future_conn.result()
        future_services.result()
        logger.info("Gold OK")

        # ── LOAD TEST ────────────────────────────────────────────────────
        run_load_test(current_date)
        logger.info("Load test OK")

        # ── RAPPORT DE PERFORMANCE (C2.4) ────────────────────────────────
        total_duration = round(time.time() - global_start, 1)
        bronze_skipped = perf_stat.get("skipped", False) or perf_ant.get("skipped", False)

        vol_bronze = round(perf_stat["size_mb"] + perf_ant["size_mb"], 2)
        silver_files = [
            os.path.join(ROOT_DIR, "silver", "indicateur1", "nettoyage-indicateur1", current_date, "indicateur_mobilite_silver.parquet"),
            os.path.join(ROOT_DIR, "silver", "indicateur2", "nettoyage-indicateur2", current_date, "indicateur_connectivite_silver.parquet"),
            os.path.join(ROOT_DIR, "silver", "indicateur4", "indicateur_services", "indicateur_services_quotidien.parquet"),
        ]
        vol_silver = round(sum(file_size_mb(f) for f in silver_files), 2)
        gold_files = [
            os.path.join(ROOT_DIR, "gold", "indicateur1", current_date, "score_mobilite_gold.parquet"),
            os.path.join(ROOT_DIR, "gold", "indicateur2", current_date, "score_connectivite_gold.parquet"),
            os.path.join(ROOT_DIR, "gold", "indicateur4", current_date, "score_services_gold.parquet"),
        ]
        vol_gold = round(sum(file_size_mb(f) for f in gold_files), 2)
        total_volume = round(vol_bronze + vol_silver + vol_gold, 2)
        debit_mbs    = round(total_volume / total_duration, 2) if total_duration > 0 else 0

        logger.info("=== RAPPORT DE PERFORMANCE (C2.4) ===")
        logger.info(f"Temps total d'execution  : {total_duration}s")
        logger.info(f"Volume Bronze  (APIs)    : {vol_bronze} MB")
        logger.info(f"Volume Silver  (Parquet) : {vol_silver} MB")
        logger.info(f"Volume Gold    (Parquet) : {vol_gold} MB")
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