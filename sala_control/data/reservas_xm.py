"""
data/reservas_xm.py — Capa de datos para el módulo "Evolución Reservas
Hídricas del SIN".

Fuente: SinergOX / API XM (librería oficial `pydataxm`), variables de
Hidrología:
  - "Volumen Útil Diario (Energía)"   -> Entity = "Sistema"  (GWh)
  - "Capacidad útil del SIN (Energía)" -> Entity = "Sistema"  (GWh)

Principios de proyecto (ver memoria):
  - Nunca hardcodear MetricId: se resuelve por nombre contra el catálogo
    vivo (`ReadDB().inventario_metricas` / `all_variables()`), con matching
    insensible a tildes.
  - pandas < 3.0 (Copy-on-Write conflicts).
  - Selección de columnas por tipo (dtype), no solo por substring del nombre.

Restricción documentada por XM: consultas diarias/horarias -> máx 30 días
por llamado. Este módulo trocea el rango solicitado en ventanas <=30 días.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

import pandas as pd

from sala_control.utils import normalize, force_writable
from sala_control.data._pydataxm_patch import aplicar_parche

aplicar_parche()  # corrige bug real de ReadDB.request_data (ver docstring del parche)

CACHE_DIR = Path(".cache/reservas")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# --- Nombres REALES confirmados contra el catálogo en vivo (ver diagnóstico) ---
# XM ya publica el % de reservas como métrica propia: no hace falta dividir
# Volumen/Capacidad a mano, evitando cualquier desfase con lo que muestra su
# propio BI (que es la fuente del gráfico de referencia).
#   PorcVoluUtilDiar  "Volumen Útil diario % por Sistema"   Entity=Sistema
VOL_PCT_KEYWORDS = ["volumen util", "diario", "%"]

# Se conservan por si en el futuro se necesitan valores absolutos en GWh
# (p. ej. para otro KPI que compare volúmenes, no solo %):
#   VoluUtilDiarEner  "Volumen Útil diario Energía por Sistema"  Entity=Sistema
#   CapaUtilDiarEner  "Capacidad Útil Energía por Sistema"       Entity=Sistema
VOL_ENER_KEYWORDS = ["volumen util", "diario", "energia"]
CAP_ENER_KEYWORDS = ["capacidad util", "energia", "sistema"]

MAX_DAYS_PER_CALL = 30  # límite documentado de la API XM para daily


# ---------------------------------------------------------------------------
# Resolución dinámica de métricas
# ---------------------------------------------------------------------------
def _catalog(api) -> pd.DataFrame:
    """Devuelve el catálogo de métricas ya normalizado con una columna
    auxiliar `_name_norm` para matching. `api` es una instancia de
    pydataxm.pydataxm.ReadDB()."""
    cat = api.inventario_metricas.copy()

    # El nombre de la columna con el nombre descriptivo de la métrica ha
    # variado entre versiones de pydataxm (p. ej. 'MetricName' / 'Name').
    # La resolvemos por inspección en vez de asumir un nombre fijo.
    name_col = next(
        (c for c in cat.columns if normalize(c) in ("metricname", "name", "nombremetrica")),
        None,
    )
    id_col = next(
        (c for c in cat.columns if normalize(c) in ("metricid", "id")),
        None,
    )
    entity_col = next((c for c in cat.columns if normalize(c) == "entity"), None)

    if name_col is None or id_col is None:
        raise RuntimeError(
            "No se pudo identificar las columnas de nombre/ID en el catálogo "
            f"de métricas de pydataxm. Columnas disponibles: {list(cat.columns)}. "
            "Ajusta `_catalog()` con los nombres reales (imprime "
            "`api.inventario_metricas.columns.tolist()` una vez en tu entorno)."
        )

    cat = cat.rename(columns={name_col: "MetricName", id_col: "MetricId"})
    if entity_col and entity_col != "Entity":
        cat = cat.rename(columns={entity_col: "Entity"})
    cat["_name_norm"] = cat["MetricName"].map(normalize)
    return cat


def resolve_metric_id(api, keywords: list[str], entity: str = "Sistema") -> str:
    """Busca en el catálogo vivo una métrica cuyo nombre contenga TODAS las
    palabras clave (insensible a tildes) y cuyo cruce incluya `entity`.
    Lanza error explícito si hay 0 o >1 coincidencias, para nunca adivinar."""
    cat = _catalog(api)
    mask = cat["_name_norm"].apply(lambda n: all(normalize(k) in n for k in keywords))
    if "Entity" in cat.columns and entity:
        mask &= cat["Entity"].astype(str).str.contains(entity, case=False, na=False)

    matches = cat.loc[mask, ["MetricId", "MetricName"]].drop_duplicates()
    if len(matches) == 0:
        raise RuntimeError(
            f"Ninguna métrica coincide con {keywords} (entity={entity}). "
            "Revisa el catálogo: puede que XM haya renombrado la variable."
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Ambigüedad resolviendo {keywords}: {matches.to_dict('records')}. "
            "Añade una palabra clave más específica."
        )
    return matches.iloc[0]["MetricId"]


# ---------------------------------------------------------------------------
# Descarga en bloques de <=30 días (restricción de la API para daily)
# ---------------------------------------------------------------------------
def _date_chunks(start: dt.date, end: dt.date, max_days: int = MAX_DAYS_PER_CALL):
    cur = start
    while cur <= end:
        chunk_end = min(cur + dt.timedelta(days=max_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + dt.timedelta(days=1)


def _value_column(df: pd.DataFrame) -> str:
    """Selecciona la columna de valor numérico diario, evitando columnas de
    texto como 'Values_code' (bug ya conocido en este proyecto)."""
    candidates = [c for c in df.columns if normalize(c) in ("value", "values_value")]
    if not candidates:
        # fallback: primera columna numérica que no sea metadata
        skip = {"id", "date", "values_code", "values_name"}
        candidates = [
            c for c in df.columns
            if normalize(c) not in skip and pd.api.types.is_numeric_dtype(df[c])
        ]
    if not candidates:
        raise RuntimeError(f"No se encontró columna de valor numérico en {df.columns.tolist()}")
    return candidates[0]


def _fetch_daily_raw(api, metric_id: str, entity: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    frames = []
    for c_start, c_end in _date_chunks(start, end):
        df = api.request_data(metric_id, entity, c_start, c_end)
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["Date", "Value"])
    raw = pd.concat(frames, ignore_index=True)
    val_col = _value_column(raw)
    date_col = next(c for c in raw.columns if normalize(c) == "date")
    out = raw[[date_col, val_col]].rename(columns={date_col: "Date", val_col: "Value"})
    out["Date"] = pd.to_datetime(out["Date"]).dt.date
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    return out.dropna(subset=["Value"]).drop_duplicates(subset=["Date"]).sort_values("Date")


# ---------------------------------------------------------------------------
# Caché incremental en parquet: solo se piden a la API los días que faltan
# ---------------------------------------------------------------------------
def _load_cache(name: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{name}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["Date", "Value"])


def _save_cache(name: str, df: pd.DataFrame) -> None:
    path = CACHE_DIR / f"{name}.parquet"
    df.sort_values("Date").drop_duplicates(subset=["Date"]).to_parquet(path, index=False)


def _incremental_fetch(api, metric_id: str, entity: str, cache_name: str,
                        start: dt.date, end: dt.date) -> pd.DataFrame:
    cached = _load_cache(cache_name)
    have_dates = set(pd.to_datetime(cached["Date"]).dt.date) if len(cached) else set()

    missing_ranges = []
    cur = start
    while cur <= end:
        if cur not in have_dates:
            run_start = cur
            while cur <= end and cur not in have_dates:
                cur += dt.timedelta(days=1)
            missing_ranges.append((run_start, cur - dt.timedelta(days=1)))
        else:
            cur += dt.timedelta(days=1)

    new_frames = []
    for r_start, r_end in missing_ranges:
        new_frames.append(_fetch_daily_raw(api, metric_id, entity, r_start, r_end))

    if new_frames:
        combined = pd.concat([cached] + new_frames, ignore_index=True)
        combined["Date"] = pd.to_datetime(combined["Date"]).dt.date
        combined = combined.drop_duplicates(subset=["Date"]).sort_values("Date")
        _save_cache(cache_name, combined)
    else:
        combined = cached

    combined["Date"] = pd.to_datetime(combined["Date"]).dt.date
    return combined[(combined["Date"] >= start) & (combined["Date"] <= end)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------
def fetch_reservas_pct(start: dt.date, end: dt.date, api=None) -> pd.DataFrame:
    """Devuelve un DataFrame diario [Date, Pct] entre `start` y `end`, usando
    caché incremental local. Usa directamente la métrica de % que publica XM
    (PorcVoluUtilDiar, Entity=Sistema) — es el mismo número que muestra su
    propio BI, sin recalcular Volumen/Capacidad por nuestra cuenta.
    """
    if api is None:
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()

    pct_id = resolve_metric_id(api, VOL_PCT_KEYWORDS, entity="Sistema")
    raw = _incremental_fetch(api, pct_id, "Sistema", "pct_reservas_sistema", start, end)
    df = raw.rename(columns={"Value": "Pct"}).dropna(subset=["Pct"]).reset_index(drop=True)

    # Defensivo: si la API devolviera fracción (0-1) en vez de porcentaje
    # (0-100), lo normalizamos. Se revisa sobre una muestra, no fila a fila,
    # para no distorsionar si hay algún día con lectura baja legítima.
    if len(df) and df["Pct"].quantile(0.95) <= 1.5:
        df["Pct"] = df["Pct"] * 100

    return df


def fetch_reservas_absolutas(start: dt.date, end: dt.date, api=None) -> pd.DataFrame:
    """Opcional / no usado por el gráfico principal: valores absolutos en GWh
    de Volumen Útil y Capacidad Útil, por si se necesitan para otro KPI.
    Aplica el mismo fallback de capacidad en dos niveles (cross-join diario,
    forward-fill donde no hay lectura de capacidad ese día)."""
    if api is None:
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()

    vol_id = resolve_metric_id(api, VOL_ENER_KEYWORDS, entity="Sistema")
    cap_id = resolve_metric_id(api, CAP_ENER_KEYWORDS, entity="Sistema")

    vol = _incremental_fetch(api, vol_id, "Sistema", "volumen_util_sistema", start, end)
    cap = _incremental_fetch(api, cap_id, "Sistema", "capacidad_util_sistema", start, end)

    vol = vol.rename(columns={"Value": "VolumenUtil_GWh"})
    cap = cap.rename(columns={"Value": "CapacidadUtil_GWh"})

    full_idx = pd.DataFrame({"Date": pd.date_range(start, end, freq="D").date})
    df = full_idx.merge(vol, on="Date", how="left").merge(cap, on="Date", how="left")

    df["CapacidadUtil_GWh"] = force_writable(df["CapacidadUtil_GWh"].to_numpy())
    df["CapacidadUtil_GWh"] = pd.Series(df["CapacidadUtil_GWh"]).ffill().bfill()
    return df.dropna(subset=["VolumenUtil_GWh"]).reset_index(drop=True)
