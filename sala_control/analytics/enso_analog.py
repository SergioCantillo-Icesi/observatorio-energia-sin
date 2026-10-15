"""
analytics/enso_analog.py — Pronóstico condicionado por ENSO (Etapa 2).

Método: analog / KNN ponderado.
  1. Se toma el estado ENSO observado más reciente (RONI) como "ancla".
  2. Para cada año hidrológico histórico, se busca su valor de RONI en el
     MISMO punto relativo del año hidrológico (mismo mes calendario que el
     ancla) — es decir, comparamos "dónde estaba el ENSO de ese año cuando
     iba en la misma fecha del año que estamos hoy".
  3. Cada año histórico recibe un peso = kernel gaussiano de la distancia
     entre su RONI-análogo y el RONI-ancla actual. Años con ENSO parecido
     al de hoy pesan más; años con ENSO opuesto pesan casi cero.
  4. Las bandas de percentil (P10/P50/P90) de reservas se recalculan como
     percentiles PONDERADOS en vez de percentiles simples — esto es lo que
     "condiciona" el envolvente climatológico al estado ENSO actual, en
     vez de tratar todos los años históricos por igual.

Esto NO es un ensamble numérico real (NMME) — es una aproximación
estadística razonable y transparente: cada año análogo conserva su peso
explícito y se puede auditar (ver `analog_weights()`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sala_control.utils import hydro_day_to_date
from sala_control.data.enso_noaa import roni_value_for, latest_observed, classify_category
from sala_control.analytics.hydro_bands import add_hydro_columns


def analog_weights(roni_df: pd.DataFrame, historical_hydro_years: list[int],
                    anchor_month: int, bandwidth: float = 0.5) -> pd.DataFrame:
    """Calcula el peso de cada año hidrológico histórico según qué tan
    parecido fue su RONI, en `anchor_month`, al RONI-ancla actual.

    Args:
        anchor_month: mes calendario del "punto de hoy" dentro del año
            hidrológico (ej. 8 si hoy es agosto).
        bandwidth: ancho del kernel gaussiano en unidades de RONI (°C).
            Más chico = solo pesan años MUY parecidos (analog set pequeño);
            más grande = se acerca a la climatología incondicional (todos
            los años pesan similar). 0.5 es un punto de partida razonable;
            ajústalo y observa cómo cambia el ancho del set de análogos.
    """
    anchor_row = latest_observed(roni_df)
    anchor_value = float(anchor_row["Anom"])

    rows = []
    for hy in historical_hydro_years:
        # Mismo mes calendario, pero en el año calendario que corresponde
        # a ese año hidrológico histórico en ese mes (dic pertenece a HY,
        # ene-nov pertenecen a HY+1).
        cal_year = hy if anchor_month == 12 else hy + 1
        analog_val = roni_value_for(roni_df, cal_year, anchor_month)
        rows.append({"HydroYear": hy, "RoniAnalogo": analog_val})

    df = pd.DataFrame(rows).dropna(subset=["RoniAnalogo"])
    df["Distancia"] = (df["RoniAnalogo"] - anchor_value).abs()
    df["Peso"] = np.exp(-0.5 * ((df["RoniAnalogo"] - anchor_value) / bandwidth) ** 2)
    df["Peso"] = df["Peso"] / df["Peso"].sum()
    df["CategoriaAnalogo"] = df["RoniAnalogo"].map(classify_category)
    df.attrs["anchor_value"] = anchor_value
    df.attrs["anchor_season"] = f"{anchor_row['Season']} {int(anchor_row['Year'])}"
    df.attrs["anchor_category"] = classify_category(anchor_value)
    return df.sort_values("Peso", ascending=False).reset_index(drop=True)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w) - 0.5 * w
    cw /= w.sum()
    return float(np.interp(q, cw, v))


def effective_sample_size(weights_df: pd.DataFrame) -> float:
    """Tamaño de muestra efectivo (Kish ESS) = 1 / sum(peso_i^2).

    Indica cuántos años "equivalentes" están realmente informando la banda
    condicionada. Si tienes 20 años históricos disponibles pero el ESS da
    2.8, en la práctica la banda se parece a solo 2-3 años reales — útil
    para decidir si conviene ampliar la ventana histórica (más candidatos
    análogos) o aumentar `bandwidth` en `analog_weights()` (pesos más
    repartidos, a costa de que años menos parecidos también cuenten)."""
    w = weights_df["Peso"].to_numpy()
    return float(1.0 / np.sum(w ** 2)) if w.sum() > 0 else 0.0


# ---------------------------------------------------------------------------
# Ponderación por TABLA DE PRONÓSTICO (preferida): usa la distribución de
# probabilidad oficial de NOAA por bin de intensidad para cada estación
# futura, en vez de un solo punto-ancla. El peso de cada año histórico varía
# mes a mes según cómo evoluciona el pronóstico.
# ---------------------------------------------------------------------------
from sala_control.data.enso_noaa import (
    STRENGTH_BIN_COLS, STRENGTH_BIN_EDGES, MONTH_TO_SEASON, roni_value_for,
)

NOMINAL_EDGE_WIDTH = 0.5  # ancho asignado a los 2 bins abiertos, solo para la densidad


def _bin_density(value: float, row: pd.Series) -> float:
    """Densidad de probabilidad (piecewise-uniforme dentro de cada bin) del
    pronóstico, evaluada en `value`. Un año cuyo RONI cae en un bin con 0%
    de probabilidad pronosticada recibe densidad ~0 — correcto: si NOAA da
    ~0% de chance de Neutral/La Niña esta temporada, un año Neutral/La Niña
    genuinamente no es un buen análogo para ESTA temporada específica."""
    for (lo, hi), col in zip(STRENGTH_BIN_EDGES, STRENGTH_BIN_COLS):
        if lo <= value < hi:
            width = hi - lo
            if width == float("inf"):
                width = NOMINAL_EDGE_WIDTH
            elif lo == float("-inf"):
                width = NOMINAL_EDGE_WIDTH
            p = row[col] / 100.0
            return p / width if width > 0 else 0.0
    return 0.0


def analog_weights_forecast(roni_df: pd.DataFrame, historical_years: list[int],
                             strength_table: pd.DataFrame, target_month: int,
                             prior_blend: float = 0.25) -> pd.DataFrame:
    """Pesos de años análogos para UN mes futuro específico, usando la fila
    de la tabla de pronóstico correspondiente a la estación centrada en
    `target_month` (ej. target_month=9 -> fila 'ASO').

    Args:
        prior_blend: fracción (0-1) de peso uniforme mezclado con el peso
            derivado del pronóstico. Existe porque cuando NOAA pronostica
            un evento récord (ej. El Niño Muy Fuerte, ≥2.0°C — solo ha
            ocurrido 2 veces en 76 años: 1997-98 y 2015-16), puede que la
            ventana histórica disponible tenga 0 o 1 año que califique. Sin
            este piso, el peso colapsa 100% en un único año histórico,
            produciendo una banda P10-P90 falsamente angosta (parece
            "segura" pero en realidad no tiene base estadística: n=1).
            0.10 = 90% del peso sigue viniendo del análogo real, 10% se
            reparte parejo entre todos los años como piso de seguridad.
            Súbelo si prefieres bandas más conservadoras/anchas; bájalo a 0
            para el peso "puro" sin piso (útil para ver qué tan extremo es
            el colapso, como diagnóstico).
    """
    season = MONTH_TO_SEASON[target_month]
    row = strength_table[strength_table["season"] == season]
    if len(row) == 0:
        raise RuntimeError(f"La tabla de pronóstico no tiene fila para la estación {season}.")
    row = row.iloc[0]

    rows = []
    for hy in historical_years:
        cal_year = hy if target_month == 12 else hy + 1
        val = roni_value_for(roni_df, cal_year, target_month)
        if val is None:
            continue
        rows.append({"HydroYear": hy, "RoniAnalogo": val, "Peso": _bin_density(val, row)})

    df = pd.DataFrame(rows)
    n = len(df)
    total = df["Peso"].sum()
    if total <= 0:
        print(f"[enso_analog] AVISO: para {season}, ningún año histórico de "
              f"{historical_years[0]}-{historical_years[-1]} cae en un bin con "
              f"probabilidad pronosticada > 0. Usando peso uniforme (revisa si "
              f"conviene ampliar la ventana histórica).")
        df["Peso"] = 1.0 / n if n else 0.0
    else:
        df["Peso"] = df["Peso"] / total
        if prior_blend > 0 and n > 0:
            df["Peso"] = (1 - prior_blend) * df["Peso"] + prior_blend * (1.0 / n)

    df["CategoriaAnalogo"] = df["RoniAnalogo"].map(classify_category)
    df.attrs["season"] = season
    df.attrs["target_month"] = target_month
    df.attrs["prior_blend"] = prior_blend
    return df.sort_values("Peso", ascending=False).reset_index(drop=True)


def compute_conditional_bands_forecast(
    df_pct: pd.DataFrame,
    roni_df: pd.DataFrame,
    strength_table: pd.DataFrame,
    historical_years: list[int],
    current_hydro_year: int,
    hydro_day_start: int,
    hydro_day_end: int,
    date_col: str = "Date",
    value_col: str = "Pct",
    prior_blend: float = 0.25,
):
    """Banda P10/P50/P90 CONDICIONADA, calculada SOLO para el rango de
    HydroDay indicado (pensado para dic-anticipado: usa hydro_day_start =
    primer día del mes siguiente al actual, para que el pronóstico empiece
    justo después del mes en curso y no se dibuje retroactivamente sobre
    meses ya observados).

    El peso de cada año histórico se recalcula por MES (no es constante
    para todo el horizonte), porque la tabla de pronóstico de NOAA cambia
    de una estación a otra.

    Returns:
        (bands_df, weights_by_month) — weights_by_month es un dict
        {mes: DataFrame de pesos} para poder auditar/mostrar el ESS de
        cada mes por separado.
    """
    hdf = add_hydro_columns(df_pct, date_col=date_col)
    historical = hdf[hdf["HydroYear"].isin(historical_years)]

    months_needed = sorted({
        hydro_day_to_date(current_hydro_year, hd).month
        for hd in range(hydro_day_start, hydro_day_end + 1)
    })
    weights_by_month = {
        m: analog_weights_forecast(roni_df, historical_years, strength_table, m, prior_blend=prior_blend)
        for m in months_needed
    }

    out = []
    for hd in range(hydro_day_start, hydro_day_end + 1):
        month = hydro_day_to_date(current_hydro_year, hd).month
        w = weights_by_month[month][["HydroYear", "Peso"]]
        g = historical[historical["HydroDay"] == hd].merge(w, on="HydroYear", how="inner")
        if len(g) == 0 or g["Peso"].sum() == 0:
            continue
        vals, wts = g[value_col].to_numpy(), g["Peso"].to_numpy()
        out.append({
            "HydroDay": hd,
            "P10_cond": _weighted_quantile(vals, wts, 0.10),
            "P50_cond": _weighted_quantile(vals, wts, 0.50),
            "P90_cond": _weighted_quantile(vals, wts, 0.90),
        })

    bands = pd.DataFrame(out).sort_values("HydroDay").reset_index(drop=True)
    return bands, weights_by_month


def compute_conditional_bands(
    df_pct: pd.DataFrame,
    weights_df: pd.DataFrame,
    date_col: str = "Date",
    value_col: str = "Pct",
) -> pd.DataFrame:
    """Recalcula P10/P50/P90 por HydroDay usando los pesos de `weights_df`
    (salida de `analog_weights`) en vez de tratar todos los años igual."""
    hdf = add_hydro_columns(df_pct, date_col=date_col)
    hdf = hdf.merge(weights_df[["HydroYear", "Peso"]], on="HydroYear", how="inner")

    out = []
    for hd, g in hdf.groupby("HydroDay"):
        vals = g[value_col].to_numpy()
        wts = g["Peso"].to_numpy()
        if len(vals) == 0 or wts.sum() == 0:
            continue
        out.append({
            "HydroDay": hd,
            "P10_cond": _weighted_quantile(vals, wts, 0.10),
            "P50_cond": _weighted_quantile(vals, wts, 0.50),
            "P90_cond": _weighted_quantile(vals, wts, 0.90),
        })
    return pd.DataFrame(out).sort_values("HydroDay").reset_index(drop=True)
