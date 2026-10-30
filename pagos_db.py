"""Persistencia de pagos procesados (idempotencia y recuperación de licencias)."""
import sqlite3
from datetime import datetime

from db_manager import DB_PATH


def init_pagos_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos (
                payment_id TEXT PRIMARY KEY,
                external_reference TEXT,
                email TEXT,
                plan TEXT,
                dias INTEGER,
                licencia TEXT NOT NULL,
                fecha TEXT NOT NULL
            )
            """
        )
        conn.commit()


def obtener_pago_guardado(payment_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT payment_id, external_reference, email, plan, dias, licencia, fecha "
            "FROM pagos WHERE payment_id = ?",
            (str(payment_id),),
        ).fetchone()
    if not row:
        return None
    keys = ("payment_id", "external_reference", "email", "plan", "dias", "licencia", "fecha")
    return dict(zip(keys, row))


def guardar_pago(payment_id, external_reference, email, plan, dias, licencia):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO pagos "
            "(payment_id, external_reference, email, plan, dias, licencia, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(payment_id), external_reference, email, plan, int(dias), licencia,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
