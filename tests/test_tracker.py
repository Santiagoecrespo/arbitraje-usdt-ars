"""Pruebas deterministas del seguimiento temporal de cotizaciones."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from config import CONFIG, ConfigError, cargar_configuracion
from storage import guardar_persistencia
from tracker import PersistenceTracker


T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _cfg(**cambios):
    return replace(CONFIG, **cambios)


def _evaluacion(origen=1_000.0, destino=1_100.0):
    return {
        "ex_compra": "lemon",
        "ex_venta": "belo",
        "precio_compra": origen,
        "precio_venta": destino,
    }


def _datos_destino(precio):
    return {"belo": {"totalBid": precio}}


def test_red_usada_invalida(monkeypatch):
    monkeypatch.setenv("RED_USADA", "red-inexistente")
    with pytest.raises(ValueError, match="RED_USADA invalida"):
        cargar_configuracion()


def test_brecha_persiste_tras_demora():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(5,)))
    observacion = tracker.registrar_si_nueva(_evaluacion(), T0)
    assert observacion is not None
    assert observacion.margen_teorico_t0_pct is not None
    assert observacion.margen_estimado_t0_pct is not None
    assert observacion.margen_conservador_t0_pct is not None
    medicion = tracker.actualizar_observaciones(_datos_destino(1_080), T0 + timedelta(minutes=5))[0]
    assert medicion["sin_dato"] is False
    assert medicion["persiste_estimado"] is True
    assert medicion["margen_estimado_post_pct"] > 0.3


def test_brecha_desaparece_tras_demora():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(5,)))
    tracker.registrar_si_nueva(_evaluacion(), T0)
    medicion = tracker.actualizar_observaciones(_datos_destino(1_005), T0 + timedelta(minutes=5))[0]
    assert medicion["sin_dato"] is False
    assert medicion["persiste_estimado"] is False


def test_inyeccion_tiempo_y_demoras_multiples_acumuladas():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(1, 3)))
    observacion = tracker.registrar_si_nueva(_evaluacion(), T0)
    assert observacion is not None
    mediciones = tracker.actualizar_observaciones(_datos_destino(1_080), T0 + timedelta(minutes=3, seconds=12))
    assert [medicion["demora_minutos"] for medicion in mediciones] == [1, 3]
    assert all(medicion["demora_real_segundos"] == pytest.approx(192) for medicion in mediciones)
    assert observacion.cerrada is True
    assert not tracker.observaciones_abiertas


def test_no_registra_duplicados_abiertos():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(5,)))
    assert tracker.registrar_si_nueva(_evaluacion(), T0) is not None
    assert tracker.registrar_si_nueva(_evaluacion(), T0 + timedelta(seconds=5)) is None
    assert len(tracker.observaciones_abiertas) == 1


def test_reapertura_de_par_tras_cierre():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(1,)))
    primera = tracker.registrar_si_nueva(_evaluacion(), T0)
    assert primera is not None
    tracker.actualizar_observaciones(_datos_destino(1_080), T0 + timedelta(minutes=1))
    segunda = tracker.registrar_si_nueva(_evaluacion(), T0 + timedelta(minutes=1, seconds=1))
    assert segunda is not None
    assert segunda.id_observacion != primera.id_observacion


def test_manejo_sin_dato_e_inicializacion_explicita():
    tracker = PersistenceTracker(_cfg(demoras_minutos=(1,)))
    tracker.registrar_si_nueva(_evaluacion(), T0)
    medicion = tracker.actualizar_observaciones({}, T0 + timedelta(minutes=1))[0]
    assert medicion["sin_dato"] is True
    assert medicion["precio_destino_post"] is None
    assert medicion["brecha_post_pct"] is None
    assert medicion["deterioro_pct"] is None
    for perfil in ("teorico", "estimado", "conservador"):
        assert medicion[f"margen_{perfil}_post_pct"] is None
        assert medicion[f"persiste_{perfil}"] is False
        assert medicion[f"no_evaluable_{perfil}"] is False
        assert medicion[f"motivo_no_evaluable_{perfil}"] is None


def test_no_evaluable_independiente_por_perfil():
    tracker = PersistenceTracker(_cfg(capital_ars=100, demoras_minutos=(1,)))
    tracker.registrar_si_nueva(_evaluacion(), T0)
    medicion = tracker.actualizar_observaciones(_datos_destino(1_080), T0 + timedelta(minutes=1))[0]
    assert medicion["no_evaluable_teorico"] is False
    assert medicion["no_evaluable_estimado"] is True
    assert medicion["no_evaluable_conservador"] is True
    estadisticas = tracker.estadisticas()["por_demora"][1]
    assert estadisticas["teorico"]["casos_validos"] == 1
    assert estadisticas["estimado"]["casos_validos"] == 0


def test_guarda_persistencia_en_csv_con_timestamps_iso(tmp_path):
    ruta = tmp_path / "persistencia.csv"
    cfg = _cfg(demoras_minutos=(1,), persistencia_csv=str(ruta))
    tracker = PersistenceTracker(cfg)
    tracker.registrar_si_nueva(_evaluacion(), T0)
    mediciones = tracker.actualizar_observaciones(_datos_destino(1_080), T0 + timedelta(minutes=1))
    guardar_persistencia(mediciones, cfg)
    contenido = ruta.read_text(encoding="utf-8")
    assert "timestamp_t0_utc" in contenido
    assert T0.isoformat() in contenido
    assert (T0 + timedelta(minutes=1)).isoformat() in contenido
