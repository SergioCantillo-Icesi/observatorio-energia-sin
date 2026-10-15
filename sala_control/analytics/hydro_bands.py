"""
analytics/hydro_bands.py — Climatología de reservas hídricas del SIN.

Replica la lógica del gráfico de referencia "Evolución Reservas Hídricas
del SIN [%]" de SinergOX:

  - Eje X = año hidrológico (dic -> nov), no año calendario.
  - Banda P10-P90 + mediana + mínimo histórico: calculados por día del año
    hidrológico usando TODOS los años históricos disponibles, EXCLUYENDO
    el año hidrológico en curso (para no contaminar el envolvente con datos
    parciales).
  - "Año de sequía 2019-2020": trayectoria específica del peor año
    hidrológico reciente, superpuesta como referencia.
  - "Volumen útil" (línea roja): valores de cierre de cada mes ya
    transcurrido del año hidrológico en curso.
  - "Volumen útil Mes Actual" (diamante rojo aislado): última lectura
    disponible dentro del mes en curso (mes aún no cerrado, por eso no se
    conecta con la línea — evita sugerir una tendencia con datos parciales).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from sala_control.utils import hydro_year, hydro_day, hydro_axis_labels


def add_hydro_columns(df: pd.DataFrame, date_col: str = "Date") -> pd.DataFrame:
    out = df.copy()
    out["HydroYear"] = out[date_col].map(hydro_year)
    out["HydroDay"] = out[date_col].map(hydro_day)
    return out


def compute_climatology(
    df_pct: pd.DataFrame,
    current_hydro_year: int,
    drought_hydro_year: int = 2019,
    value_col: str = "Pct",
    date_col: str = "Date",
) -> dict:
    """
    Args:
        df_pct: DataFrame diario con columnas [date_col, value_col].
        current_hydro_year: año hidrológico "en curso" a excluir del cálculo
            de bandas (ej. 2025 para la ventana dic-2025..nov-2026).
        drought_hydro_year: año hidrológico a resaltar como "año de sequía"
            (por defecto 2019 = dic-2019..nov-2020, el peor reciente).

    Returns:
        dict con:
          'labels'   -> DataFrame de meses del eje X (hydro_day, label)
          'bands'    -> DataFrame indexado por hydro_day con P10, P50, Min, Max
          'drought'  -> DataFrame [hydro_day, value] del año de sequía
          'current'  -> DataFrame [hydro_day, value] del año en curso (completo)
    """
    hdf = add_hydro_columns(df_pct, date_col=date_col)

    historical = hdf[hdf["HydroYear"] != current_hydro_year]
    bands = (
        historical.groupby("HydroDay")[value_col]
        .agg(P10=lambda s: s.quantile(0.10),
             P50="median",
             Min="min",
             Max="max",
             P90=lambda s: s.quantile(0.90))
        .reset_index()
        .sort_values("HydroDay")
    )

    drought = (
        hdf[hdf["HydroYear"] == drought_hydro_year][["HydroDay", value_col]]
        .rename(columns={value_col: "value"})
        .sort_values("HydroDay")
    )

    current = (
        hdf[hdf["HydroYear"] == current_hydro_year][["HydroDay", value_col, date_col]]
        .rename(columns={value_col: "value"})
        .sort_values("HydroDay")
    )

    return {
        "labels": hydro_axis_labels(current_hydro_year),
        "bands": bands,
        "drought": drought,
        "current": current,
    }


def split_current_year_series(current: pd.DataFrame, today: dt.date,
                               date_col: str = "Date") -> dict:
    """Separa la serie del año en curso en:
      - 'closed_months': un punto por cada mes YA CERRADO (último valor
        disponible de ese mes) -> se dibuja como línea con marcadores.
      - 'current_point': último valor disponible dentro del mes en curso
        (mes todavía abierto) -> se dibuja como marcador aislado.
    Si `today` cae en el día 1 del mes (sin datos aún ese mes), current_point
    puede quedar vacío y basta con mostrar closed_months.
    """
    cur = current.copy()
    cur[date_col] = pd.to_datetime(cur[date_col])
    cur["year_month"] = cur[date_col].dt.to_period("M")
    this_month = pd.Period(today, freq="M")

    closed = cur[cur["year_month"] < this_month]
    open_month = cur[cur["year_month"] == this_month]

    closed_months = (
        closed.sort_values(date_col)
        .groupby("year_month")
        .tail(1)[["HydroDay", "value", date_col]]
        .sort_values("HydroDay")
        .reset_index(drop=True)
    )

    current_point = (
        open_month.sort_values(date_col).tail(1)[["HydroDay", "value", date_col]]
        .reset_index(drop=True)
    )

    return {"closed_months": closed_months, "current_point": current_point}
