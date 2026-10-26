"""IRFEN · emparejamiento pluviómetro–IMERG, evaluación y calibración experimental (RESEARCH_ONLY / TEST_ONLY).

Paquete científico offline y desacoplado del visor v0.9: no abre conexiones de red, no escribe fuera del directorio de
salida indicado, no publica, no alerta y no cambia umbrales, geometrías ni clasificaciones de riesgo.

Módulos
-------
grid         Convenciones de la malla IMERG V07 (0,1°), celda que contiene una estación y vecindad 3×3.
granules     Identidad de gránulos IMERG medio-horarios (producto, corrida, versión, intervalo) desde el nombre.
imerg_cells  Lectura de HDF5 locales y extracción de la celda de cada estación (requiere h5py y numpy).
observations Registro de lecturas de pluviómetro con procedencia, ventana, calidad y elegibilidad.
pairing      Reconstrucción de acumulados IMERG en la ventana exacta del pluviómetro y pares con linaje.
evaluate     Métricas continuas y categóricas, estratos y bootstrap por días solo cuando es defendible.
calibrate    Línea base y correcciones simples con compuertas de muestra y validación sin fuga temporal.
"""

SCHEMA_VERSION = "1.0.0"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "operational_alerting_enabled": False,
    "map_publishable": False,
    "changes_thresholds_or_geometries": False,
    "network_access": False,
}
