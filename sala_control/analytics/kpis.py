"""
analytics/kpis.py — KPIs de decisión para agentes del mercado, derivados del
pipeline de reservas + climatología + pronóstico condicionado ENSO.

Ninguno de estos 4 números existe en SinergOX/XM tal cual — se calculan a
partir de lo que ya construimos en los módulos anteriores:

  1. Proyección al cierre del año hidrológico -> hacia dónde se espera que
     vayan las reservas y cuánto (mediana del pronóstico condicionado por
     ENSO), no solo dónde están hoy. Directamente accionable para
     planeación.
  2. Margen sobre el mínimo histórico (pp) -> colchón inmediato de riesgo,
     SIEMPRE calculable (a diferencia de un "días hasta cruce", que casi
     siempre da "sin cruce" y no aporta nada como titular de tarjeta).
  3. Probabilidad implícita de cerrar en niveles del peor El Niño histórico
     o peor -> traduce la banda condicionada en un número de riesgo
     accionable, comparado contra el peor cierre observado entre años que
     SÍ fueron El Niño (no un año fijo arbitrario como "sequía 2019-2020",
     que ni siquiera fue un año El Niño según el RONI real).
  4. Ritmo de recuperación (30d) vs. típico -> señal de momentum, 100%
     sobre datos observados (no depende del pronóstico ENSO).

IMPORTANTE — robustez a datos reales: XM puede tener rezago de publicación
(la fecha calendario de "hoy" puede no tener dato todavía) o huecos
puntuales en el histórico. Por eso NINGUNA función de este módulo exige una
coincidencia EXACTA de HydroDay — todas buscan el día disponible más
cercano dentro de una tolerancia (`tolerance_days`, default 3). El llamador
debe pasar como `reference_date` la fecha MÁS RECIENTE con dato real
(`df["Date"].max()`), no necesariamente `date.today()`.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from sala_control.analytics.hydro_bands import add_hydro_columns
from sala_control.utils import hydro_day, hydro_year as _hydro_year_of_date


def _nearest_value(df_year: pd.DataFrame, target_hd: int, value_col: str,
                    tolerance_days: int = 3) -> tuple[float | None, int | None]:
    """Valor en el HydroDay disponible más cercano a `target_hd`, dentro de
    ±tolerance_days. Devuelve (valor, hydro_day_encontrado) o (None, None)
    si no hay nada dentro de la tolerancia."""
    window = df_year[(df_year["HydroDay"] >= target_hd - tolerance_days) &
                      (df_year["HydroDay"] <= target_hd + tolerance_days)]
    if len(window) == 0:
        return None, None
    window = window.copy()
    window["_dist"] = (window["HydroDay"] - target_hd).abs()
    row = window.sort_values("_dist").iloc[0]
    return float(row[value_col]), int(row["HydroDay"])


def historical_percentile(df_pct: pd.DataFrame, current_hydro_year: int, reference_date,
                           date_col: str = "Date", value_col: str = "Pct",
                           tolerance_days: int = 3) -> float | None:
    """Percentil (0-100) del valor MÁS RECIENTE disponible frente a la
    distribución empírica completa de todos los años históricos, en la
    MISMA época del año hidrológico. `reference_date` debe ser la fecha más
    reciente con dato real (df["Date"].max()), no necesariamente hoy."""
    hdf = add_hydro_columns(df_pct, date_col=date_col)
    hd_ref = hydro_day(reference_date)

    cur = hdf[hdf["HydroYear"] == current_hydro_year]
    cur_val, hd_found = _nearest_value(cur, hd_ref, value_col, tolerance_days)
    if cur_val is None:
        return None

    historical = hdf[hdf["HydroYear"] != current_hydro_year]
    historical_vals = historical[historical["HydroDay"] == hd_found][value_col]
    if len(historical_vals) == 0:
        return None
    return float((historical_vals < cur_val).mean() * 100)


def projected_year_end_level(df_pct: pd.DataFrame, cond_bands: pd.DataFrame,
                              current_hydro_year: int, reference_date,
                              date_col: str = "Date", value_col: str = "Pct",
                              tolerance_days: int = 3) -> dict | None:
    """Proyección al cierre del año hidrológico: nivel esperado (mediana del
    pronóstico condicionado por ENSO en el último día del horizonte de
    pronóstico) y el cambio esperado en pp respecto al nivel MÁS RECIENTE
    disponible. A diferencia del percentil histórico (que solo contextualiza
    dónde estás hoy), esto dice hacia dónde se espera que vayan las reservas
    y cuánto — información directamente accionable para planeación
    (cobertura, despacho térmico esperado, etc.).

    Returns:
        dict {current, projected, delta, p10, p90} o None si no hay banda
        condicionada disponible (ej. si ya estamos en el último mes del año
        hidrológico y no queda nada por pronosticar).
    """
    if cond_bands is None or len(cond_bands) == 0:
        return None

    hdf = add_hydro_columns(df_pct, date_col=date_col)
    hd_ref = hydro_day(reference_date)
    cur = hdf[hdf["HydroYear"] == current_hydro_year]
    cur_val, _ = _nearest_value(cur, hd_ref, value_col, tolerance_days)
    if cur_val is None:
        return None

    last_row = cond_bands.sort_values("HydroDay").iloc[-1]
    projected = float(last_row["P50_cond"])
    return {
        "current": cur_val,
        "projected": projected,
        "delta": projected - cur_val,
        "p10": float(last_row["P10_cond"]),
        "p90": float(last_row["P90_cond"]),
    }


def margin_over_historical_min(df_pct: pd.DataFrame, min_by_hydroday: pd.Series,
                                current_hydro_year: int, reference_date,
                                date_col: str = "Date", value_col: str = "Pct",
                                tolerance_days: int = 3) -> float | None:
    """Diferencia en puntos porcentuales entre el valor MÁS RECIENTE
    disponible y el mínimo histórico registrado para esa misma época del
    año. A diferencia de un "días hasta cruzar el mínimo" (que casi siempre
    da "sin cruce" porque el escenario central rara vez llega tan bajo),
    esto SIEMPRE da un número: qué tan cerca o lejos estás del peor registro
    histórico, hoy mismo. Menor margen = más urgente."""
    hdf = add_hydro_columns(df_pct, date_col=date_col)
    hd_ref = hydro_day(reference_date)

    cur = hdf[hdf["HydroYear"] == current_hydro_year]
    cur_val, hd_found = _nearest_value(cur, hd_ref, value_col, tolerance_days)
    if cur_val is None:
        return None

    min_val = min_by_hydroday.get(hd_found)
    if min_val is None:
        return None
    return float(cur_val - min_val)


def implied_probability_at_or_below(value: float, p10: float, p50: float, p90: float) -> float | None:
    """Interpola linealmente en el espacio de cuantiles (P10/P50/P90) para
    estimar la probabilidad implícita de terminar en `value` o por debajo,
    según la banda condicionada. Devuelve None si `value` cae fuera del
    rango modelado (< P10 o > P90) — en vez de extrapolar un número sin
    respaldo, se reporta como '<10%' o '>90%' en la UI."""
    if p10 is None or p50 is None or p90 is None:
        return None
    if value <= p10:
        return None  # <10%
    if value >= p90:
        return None  # >90%
    if value < p50:
        return 0.10 + (value - p10) / (p50 - p10) * 0.40
    return 0.50 + (value - p50) / (p90 - p50) * 0.40


def worst_el_nino_closing(df_pct: pd.DataFrame, roni_df: pd.DataFrame, historical_years: list[int],
                           hd_end: int, el_nino_threshold: float = 0.5,
                           date_col: str = "Date", value_col: str = "Pct",
                           tolerance_days: int = 3) -> dict | None:
    """Encuentra, entre los años históricos que SÍ fueron El Niño (RONI pico
    >= el_nino_threshold en algún momento de ese año hidrológico), cuál tuvo
    el peor (menor) nivel de reservas al cierre del año hidrológico
    (HydroDay=hd_end). Reemplaza la comparación contra un año fijo arbitrario
    (ej. "sequía 2019-2020", que según el RONI real ni siquiera fue El Niño
    — llegó apenas a 0.22, prácticamente Neutral) por una comparación
    apples-to-apples: el peor cierre observado en años que sí tuvieron la
    misma condición climática que estamos viviendo ahora.

    Returns:
        dict con {hydro_year, category, peak_roni, value} del peor año
        El Niño encontrado, o None si no hay ninguno en la ventana histórica
        disponible (ej. si `historical_years` no alcanza a cubrir 2015-16
        ni 1997-98 — los únicos "Muy Fuerte" del registro 1950-2026).
    """
    from sala_control.data.enso_noaa import classify_category

    roni = roni_df.copy()
    roni["HydroYear"] = roni.apply(
        lambda r: _hydro_year_of_date(dt.date(int(r["Year"]), int(r["CenterMonth"]), 15)), axis=1
    )
    peak_by_year = roni.loc[roni.groupby("HydroYear")["Anom"].idxmax()][["HydroYear", "Anom"]]
    peak_by_year = peak_by_year.set_index("HydroYear")["Anom"]

    hdf = add_hydro_columns(df_pct, date_col=date_col)

    candidates = []
    for hy in historical_years:
        peak = peak_by_year.get(hy)
        if peak is None or peak < el_nino_threshold:
            continue  # no fue año El Niño
        g = hdf[hdf["HydroYear"] == hy]
        val, hd_found = _nearest_value(g, hd_end, value_col, tolerance_days)
        if val is None:
            continue
        candidates.append({"hydro_year": hy, "category": classify_category(peak),
                            "peak_roni": float(peak), "value": val})

    if not candidates:
        return None
    return min(candidates, key=lambda c: c["value"])


def reliability_label(ess: float) -> str:
    """Etiqueta cualitativa simple para el ESS (se usa en el expander de
    detalle técnico, ya no como KPI principal)."""
    if ess < 3:
        return "Baja"
    if ess < 8:
        return "Media"
    return "Alta"


def recent_trend_vs_historical(df_pct: pd.DataFrame, current_hydro_year: int, reference_date,
                                window_days: int = 30, date_col: str = "Date",
                                value_col: str = "Pct",
                                tolerance_days: int = 3) -> tuple[float | None, float | None]:
    """Ritmo de cambio (pp/mes) de los últimos `window_days` días, comparado
    contra el ritmo típico histórico para la MISMA ventana de fechas del
    año hidrológico (promedio de todos los años históricos disponibles).

    No depende del pronóstico condicionado por ENSO — se calcula 100% sobre
    datos ya observados. Señal de momentum: si el llenado va más lento que
    lo típico para esta época, es alerta temprana aunque el nivel absoluto
    de hoy todavía se vea bien.

    Returns:
        (ritmo_actual_pp_mes, ritmo_historico_tipico_pp_mes) — cualquiera
        puede ser None si no hay suficiente dato para calcularlo.
    """
    hdf = add_hydro_columns(df_pct, date_col=date_col)
    hd_ref = hydro_day(reference_date)
    hd_start_target = hd_ref - window_days
    if hd_start_target < 0:
        return None, None

    cur = hdf[hdf["HydroYear"] == current_hydro_year]
    val_ref, hd_ref_found = _nearest_value(cur, hd_ref, value_col, tolerance_days)
    val_start, hd_start_found = _nearest_value(cur, hd_start_target, value_col, tolerance_days)
    if val_ref is None or val_start is None:
        return None, None
    actual_window = hd_ref_found - hd_start_found
    if actual_window <= 0:
        return None, None
    current_rate = (val_ref - val_start) / actual_window * 30

    hist = hdf[hdf["HydroYear"] != current_hydro_year]
    rates = []
    for hy, g in hist.groupby("HydroYear"):
        a_val, a_hd = _nearest_value(g, hd_ref, value_col, tolerance_days)
        b_val, b_hd = _nearest_value(g, hd_start_target, value_col, tolerance_days)
        if a_val is not None and b_val is not None and (a_hd - b_hd) > 0:
            rates.append((a_val - b_val) / (a_hd - b_hd) * 30)

    historical_rate = float(sum(rates) / len(rates)) if rates else None
    return current_rate, historical_rate
