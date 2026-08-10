"""Seguimiento temporal de persistencia para diferencias de cotizaciones publicas."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import uuid4

from calculator import calcular_margen
from config import Config


PERFILES = ("teorico", "estimado", "conservador")


@dataclass
class BrechaObservada:
    """Una diferencia registrada en T0 y sus mediciones temporales pendientes."""

    id_observacion: str
    timestamp_t0_utc: datetime
    ex_origen: str
    ex_destino: str
    precio_origen_t0: float
    precio_destino_t0: float
    brecha_bruta_t0_pct: float
    margen_teorico_t0_pct: float | None
    margen_estimado_t0_pct: float | None
    margen_conservador_t0_pct: float | None
    demoras_pendientes: list[int]
    observaciones: list[dict[str, Any]] = field(default_factory=list)
    cerrada: bool = False


class PersistenceTracker:
    """Mantiene observaciones abiertas y genera mediciones para cada demora vencida."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._perfiles = cfg.perfiles
        self._abiertas: list[BrechaObservada] = []
        self._cerradas: deque[BrechaObservada] = deque(maxlen=cfg.historial_persistencia_max)
        self._mediciones: deque[dict[str, Any]] = deque(maxlen=cfg.historial_persistencia_max)

    @property
    def observaciones_abiertas(self) -> tuple[BrechaObservada, ...]:
        """Vista inmutable de las observaciones que aun tienen demoras pendientes."""
        return tuple(self._abiertas)

    @staticmethod
    def _ahora_utc(ahora_utc: datetime | None) -> datetime:
        ahora = ahora_utc or datetime.now(timezone.utc)
        if ahora.tzinfo is None:
            raise ValueError("Los timestamps del tracker deben incluir timezone.utc")
        return ahora.astimezone(timezone.utc)

    @staticmethod
    def _numero_positivo(valor: object) -> float | None:
        try:
            numero = float(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return numero if isfinite(numero) and numero > 0 else None

    def _margen_perfil(self, precio_origen: float, precio_destino: float, nombre: str) -> float | None:
        resultado = calcular_margen(
            precio_origen,
            precio_destino,
            self.cfg,
            perfil=self._perfiles[nombre],
        )
        return None if resultado is None else float(resultado["margen_neto_pct"])

    def registrar_si_nueva(
        self,
        evaluacion_par: Mapping[str, Any],
        ahora_utc: datetime | None = None,
    ) -> BrechaObservada | None:
        """Abre una sola observacion por par si supera la brecha minima configurada."""
        ex_origen = evaluacion_par.get("ex_origen", evaluacion_par.get("ex_compra"))
        ex_destino = evaluacion_par.get("ex_destino", evaluacion_par.get("ex_venta"))
        precio_origen = self._numero_positivo(
            evaluacion_par.get("precio_origen", evaluacion_par.get("precio_compra"))
        )
        precio_destino = self._numero_positivo(
            evaluacion_par.get("precio_destino", evaluacion_par.get("precio_venta"))
        )
        if not isinstance(ex_origen, str) or not isinstance(ex_destino, str):
            return None
        if precio_origen is None or precio_destino is None:
            return None

        brecha_t0 = (precio_destino - precio_origen) / precio_origen * 100
        if brecha_t0 < self.cfg.brecha_minima_registro_pct:
            return None
        if any(obs.ex_origen == ex_origen and obs.ex_destino == ex_destino for obs in self._abiertas):
            return None

        observacion = BrechaObservada(
            id_observacion=str(uuid4()),
            timestamp_t0_utc=self._ahora_utc(ahora_utc),
            ex_origen=ex_origen,
            ex_destino=ex_destino,
            precio_origen_t0=precio_origen,
            precio_destino_t0=precio_destino,
            brecha_bruta_t0_pct=brecha_t0,
            margen_teorico_t0_pct=self._margen_perfil(precio_origen, precio_destino, "teorico"),
            margen_estimado_t0_pct=self._margen_perfil(precio_origen, precio_destino, "estimado"),
            margen_conservador_t0_pct=self._margen_perfil(precio_origen, precio_destino, "conservador"),
            demoras_pendientes=list(self.cfg.demoras_minutos),
        )
        self._abiertas.append(observacion)
        return observacion

    def _precio_destino_actual(self, datos_actuales: Mapping[str, Any], exchange: str) -> float | None:
        info = datos_actuales.get(exchange)
        if not isinstance(info, Mapping):
            return None
        return self._numero_positivo(info.get("totalBid") or info.get("bid"))

    def _medicion(
        self,
        observacion: BrechaObservada,
        demora_minutos: int,
        datos_actuales: Mapping[str, Any],
        ahora: datetime,
    ) -> dict[str, Any]:
        demora_real_segundos = (ahora - observacion.timestamp_t0_utc).total_seconds()
        precio_destino_actual = self._precio_destino_actual(datos_actuales, observacion.ex_destino)

        if precio_destino_actual is None:
            sin_dato = True
            precio_destino_post = None
            brecha_post_pct = None
            deterioro_pct = None
            margen_teorico_post_pct = None
            margen_estimado_post_pct = None
            margen_conservador_post_pct = None
            persiste_teorico = False
            persiste_estimado = False
            persiste_conservador = False
            no_evaluable_teorico = False
            no_evaluable_estimado = False
            no_evaluable_conservador = False
            motivo_no_evaluable_teorico = None
            motivo_no_evaluable_estimado = None
            motivo_no_evaluable_conservador = None
        else:
            sin_dato = False
            precio_destino_post = precio_destino_actual
            brecha_post_pct = (
                (precio_destino_post - observacion.precio_origen_t0)
                / observacion.precio_origen_t0
                * 100
            )
            deterioro_pct = brecha_post_pct - observacion.brecha_bruta_t0_pct

            margenes: dict[str, float | None] = {}
            no_evaluables: dict[str, bool] = {}
            motivos: dict[str, str | None] = {}
            persistencias: dict[str, bool] = {}
            for nombre in PERFILES:
                margen = self._margen_perfil(
                    observacion.precio_origen_t0,
                    precio_destino_post,
                    nombre,
                )
                margenes[nombre] = margen
                no_evaluables[nombre] = margen is None
                motivos[nombre] = "Costo supera saldo / Retorno nulo" if margen is None else None
                persistencias[nombre] = bool(
                    margen is not None and margen >= self.cfg.margen_minimo_pct
                )

            margen_teorico_post_pct = margenes["teorico"]
            margen_estimado_post_pct = margenes["estimado"]
            margen_conservador_post_pct = margenes["conservador"]
            persiste_teorico = persistencias["teorico"]
            persiste_estimado = persistencias["estimado"]
            persiste_conservador = persistencias["conservador"]
            no_evaluable_teorico = no_evaluables["teorico"]
            no_evaluable_estimado = no_evaluables["estimado"]
            no_evaluable_conservador = no_evaluables["conservador"]
            motivo_no_evaluable_teorico = motivos["teorico"]
            motivo_no_evaluable_estimado = motivos["estimado"]
            motivo_no_evaluable_conservador = motivos["conservador"]

        return {
            "id_observacion": observacion.id_observacion,
            "version_supuestos": self.cfg.version_supuestos,
            "timestamp_t0_utc": observacion.timestamp_t0_utc,
            "timestamp_medicion_utc": ahora,
            "ex_origen": observacion.ex_origen,
            "ex_destino": observacion.ex_destino,
            "precio_origen_t0": observacion.precio_origen_t0,
            "precio_destino_t0": observacion.precio_destino_t0,
            "brecha_bruta_t0_pct": observacion.brecha_bruta_t0_pct,
            "margen_teorico_t0_pct": observacion.margen_teorico_t0_pct,
            "margen_estimado_t0_pct": observacion.margen_estimado_t0_pct,
            "margen_conservador_t0_pct": observacion.margen_conservador_t0_pct,
            "demora_minutos": demora_minutos,
            "demora_real_segundos": demora_real_segundos,
            "precio_destino_post": precio_destino_post,
            "brecha_post_pct": brecha_post_pct,
            "deterioro_pct": deterioro_pct,
            "margen_teorico_post_pct": margen_teorico_post_pct,
            "margen_estimado_post_pct": margen_estimado_post_pct,
            "margen_conservador_post_pct": margen_conservador_post_pct,
            "persiste_teorico": persiste_teorico,
            "persiste_estimado": persiste_estimado,
            "persiste_conservador": persiste_conservador,
            "sin_dato": sin_dato,
            "no_evaluable_teorico": no_evaluable_teorico,
            "no_evaluable_estimado": no_evaluable_estimado,
            "no_evaluable_conservador": no_evaluable_conservador,
            "motivo_no_evaluable_teorico": motivo_no_evaluable_teorico,
            "motivo_no_evaluable_estimado": motivo_no_evaluable_estimado,
            "motivo_no_evaluable_conservador": motivo_no_evaluable_conservador,
        }

    def actualizar_observaciones(
        self,
        datos_actuales: Mapping[str, Any],
        ahora_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Genera una medicion por cada demora vencida usando el mismo ciclo actual."""
        ahora = self._ahora_utc(ahora_utc)
        nuevas_mediciones: list[dict[str, Any]] = []
        for observacion in list(self._abiertas):
            demora_transcurrida = (ahora - observacion.timestamp_t0_utc).total_seconds()
            vencidas = [
                demora
                for demora in observacion.demoras_pendientes
                if demora_transcurrida >= demora * 60
            ]
            for demora in vencidas:
                medicion = self._medicion(observacion, demora, datos_actuales, ahora)
                observacion.demoras_pendientes.remove(demora)
                observacion.observaciones.append(medicion)
                self._mediciones.append(medicion)
                nuevas_mediciones.append(medicion)
            if not observacion.demoras_pendientes:
                observacion.cerrada = True
                self._abiertas.remove(observacion)
                self._cerradas.append(observacion)
        return nuevas_mediciones

    def estadisticas(self) -> dict[str, Any]:
        """Resume persistencia por perfil y demora, excluyendo casos no evaluables."""
        mediciones = list(self._mediciones)
        por_demora: dict[int, dict[str, dict[str, float | int | None]]] = {}
        deterioro_promedio_por_demora: dict[int, float | None] = {}
        for demora in self.cfg.demoras_minutos:
            registros = [registro for registro in mediciones if registro["demora_minutos"] == demora]
            por_demora[demora] = {}
            deterioros = [
                float(registro["deterioro_pct"])
                for registro in registros
                if registro["deterioro_pct"] is not None
            ]
            deterioro_promedio_por_demora[demora] = (
                sum(deterioros) / len(deterioros) if deterioros else None
            )
            for perfil in PERFILES:
                validos = [
                    registro
                    for registro in registros
                    if not registro["sin_dato"] and not registro[f"no_evaluable_{perfil}"]
                ]
                persistentes = sum(bool(registro[f"persiste_{perfil}"]) for registro in validos)
                por_demora[demora][perfil] = {
                    "casos_validos": len(validos),
                    "casos_persistentes": persistentes,
                    "pct_persistencia": (
                        persistentes / len(validos) * 100 if validos else None
                    ),
                }

        demora_referencia = 5 if 5 in self.cfg.demoras_minutos else self.cfg.demoras_minutos[0]
        pares: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for registro in mediciones:
            if (
                registro["demora_minutos"] == demora_referencia
                and not registro["sin_dato"]
                and not registro["no_evaluable_estimado"]
            ):
                pares[(str(registro["ex_origen"]), str(registro["ex_destino"]))].append(registro)
        mejor_par: dict[str, Any] | None = None
        if pares:
            par, registros = max(
                pares.items(),
                key=lambda item: sum(bool(r["persiste_estimado"]) for r in item[1]) / len(item[1]),
            )
            porcentaje = sum(bool(r["persiste_estimado"]) for r in registros) / len(registros) * 100
            mejor_par = {
                "ex_origen": par[0],
                "ex_destino": par[1],
                "demora_minutos": demora_referencia,
                "perfil": "estimado",
                "pct_persistencia": porcentaje,
            }

        return {
            "total_observaciones": len(mediciones),
            "total_sin_dato": sum(bool(registro["sin_dato"]) for registro in mediciones),
            "observaciones_abiertas": len(self._abiertas),
            "por_demora": por_demora,
            "deterioro_promedio_por_demora": deterioro_promedio_por_demora,
            "par_mayor_persistencia": mejor_par,
        }
