"""Pruebas de rutas locales y rutas inyectadas para despliegues persistentes."""

import config as config_module


RUTAS_SALIDA = ("CSV_SALIDA", "PERSISTENCIA_CSV", "LOG_ERRORES")


def _sin_archivo_env(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda *_args, **_kwargs: False)


def test_rutas_de_salida_locales_por_defecto(monkeypatch):
    _sin_archivo_env(monkeypatch)
    for nombre in RUTAS_SALIDA:
        monkeypatch.delenv(nombre, raising=False)

    cfg = config_module.cargar_configuracion()

    assert cfg.csv_salida == "arbitraje_log.csv"
    assert cfg.persistencia_csv == "persistencia_log.csv"
    assert cfg.log_errores == "errores.log"


def test_rutas_de_salida_se_sobrescriben_por_entorno(monkeypatch):
    _sin_archivo_env(monkeypatch)
    monkeypatch.setenv("CSV_SALIDA", "/data/arbitraje_log.csv")
    monkeypatch.setenv("PERSISTENCIA_CSV", "/data/persistencia_log.csv")
    monkeypatch.setenv("LOG_ERRORES", "/data/errores.log")

    cfg = config_module.cargar_configuracion()

    assert cfg.csv_salida == "/data/arbitraje_log.csv"
    assert cfg.persistencia_csv == "/data/persistencia_log.csv"
    assert cfg.log_errores == "/data/errores.log"
