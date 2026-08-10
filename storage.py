"""Persistencia local de resultados de paper trading y errores operativos."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from config import Config


CSV_FIELDS = (
    "cycle_id",
    "timestamp_utc",
    "duracion_calculo_ms",
    "ex_compra",
    "ex_venta",
    "precio_compra",
    "precio_venta",
    "red",
    "brecha_bruta_pct",
    "margen_neto_pct",
    "ganancia_ars",
    "carga_fiscal_ars",
    "gas_fee_usdt",
)


def loguear_error(mensaje: str, log_file: str) -> None:
    """Agrega un error con timestamp UTC; no deja caer el loop si falla el log."""
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    try:
        with Path(log_file).open("a", encoding="utf-8") as archivo:
            archivo.write(f"[{timestamp_utc}] {mensaje}\n")
    except OSError:
        # El error original ya puede haberse mostrado por consola en el llamador.
        pass


def guardar_ciclo(
    cycle_id: int,
    timestamp_utc: str,
    duracion_ms: int,
    oportunidades: Sequence[dict[str, Any]],
    cfg: Config,
) -> None:
    """Guarda las tres mejores oportunidades de un ciclo en un CSV local."""
    ruta = Path(cfg.csv_salida)
    existe = ruta.is_file()
    try:
        with ruta.open("a", newline="", encoding="utf-8") as archivo:
            writer = csv.DictWriter(archivo, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if not existe:
                writer.writeheader()
            for oportunidad in oportunidades[:3]:
                writer.writerow(
                    {
                        "cycle_id": cycle_id,
                        "timestamp_utc": timestamp_utc,
                        "duracion_calculo_ms": duracion_ms,
                        **oportunidad,
                    }
                )
    except PermissionError:
        loguear_error("CSV abierto o bloqueado; se omite este ciclo", cfg.log_errores)
    except OSError as exc:
        loguear_error(f"No se pudo escribir el CSV: {exc}", cfg.log_errores)
