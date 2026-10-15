"""
charts/reservas_chart.py — Figura Plotly "Evolución Reservas Hídricas del SIN [%]"

Estilo ICESI: paleta tomada del manual de identidad institucional vigente
(https://www.icesi.edu.co/wp-content/uploads/2026/03/Manual-de-marca-institucional-Icesi.pdf):
  - Azul Icesi: Pantone 2131 C = RGB(84,84,233) = #5454E9 (color oficial
    confirmado en el manual — NO uses conversores genéricos de Pantone a
    HEX, dan un azul distinto).
  - Paleta principal institucional = solo Azul Icesi + Blanco.
  - Gris 1 (Pantone 423 C, ≈ #898D8D) como neutro de apoyo, documentado en
    los manuales de facultades/centros para textos secundarios.
  - Tipografía: Plus Jakarta Sans (la usa el manual para descriptores).

Contraste: las etiquetas de % ya NO son `text` de trace (que se pierden
contra las bandas de color) — son `add_annotation()` con fondo blanco
opaco, así se leen sin importar qué banda tengan detrás.
"""
from __future__ import annotations

import plotly.graph_objects as go

from sala_control.utils import fmt_pct_co
from sala_control.theme import (
    ICESI_BLUE, ICESI_BLUE_DARK, ICESI_GRAY, ICESI_GRAY_LIGHT, ICESI_ALERT, FONT_FAMILY,
)

COLOR_BAND_FILL = "rgba(84, 84, 233, 0.12)"   # tinte muy claro del Azul Icesi
COLOR_P10 = "#E67E22"           # naranja
COLOR_P90 = "#00B4D8"           # azul cian vivo — distinto a ICESI_BLUE/ICESI_BLUE_DARK
                                 # (Volumen útil / Mediana condicionada ENSO), a propósito,
                                 # para que resalte en vez de mezclarse con esos dos.
COLOR_MIN_HIST = ICESI_ALERT    # rojo
COLOR_MEDIANA = "#F2C94C"       # amarillo
COLOR_ACTUAL = ICESI_BLUE

def _hover_pct(label: str) -> str:
    """hovertemplate de una serie: '<nombre>: <valor sin decimales>%'.

    En hovermode="x unified", un hovertemplate personalizado con
    `<extra></extra>` vacío suprime el nombre que Plotly antepondría por
    defecto a cada fila (confirmado en la práctica: sin esto, el cuadro de
    hover mostraba el % correcto pero sin decir de qué categoría era) — por
    eso el nombre va DENTRO del propio texto. El "%" final es literal (no
    el operador de formato de d3, que multiplicaría por 100 — los valores
    ya vienen en escala 0-100)."""
    return f"{label}: %{{y:.0f}}%<extra></extra>"


def _add_pct_labels(fig: go.Figure, x_vals, y_vals, color: str = ICESI_BLUE) -> None:
    """Etiquetas de % como anotaciones con chip blanco de fondo — nunca se
    pierden contra las bandas de color, a diferencia de `text` en un trace."""
    for x, y in zip(x_vals, y_vals):
        fig.add_annotation(
            x=x, y=y, text=fmt_pct_co(y), showarrow=False,
            yshift=16, font=dict(size=11, color=color, family=FONT_FAMILY),
            bgcolor="rgba(255,255,255,0.85)", bordercolor="rgba(0,0,0,0)",
            borderpad=2,
        )


def build_reservas_figure(climatology: dict, current_split: dict) -> go.Figure:
    labels = climatology["labels"]
    bands = climatology["bands"]

    fig = go.Figure()

    # --- Banda P10-P90 (relleno) ---
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["P90"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["P10"], mode="lines",
        line=dict(width=0), fill="tonexty", fillcolor=COLOR_BAND_FILL,
        showlegend=False, hoverinfo="skip",
    ))

    # --- Líneas de referencia punteadas ---
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["P10"], mode="lines", name="P10",
        line=dict(color=COLOR_P10, width=1.3, dash="dot"),
        hovertemplate=_hover_pct("P10"),
    ))
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["P90"], mode="lines", name="P90",
        line=dict(color=COLOR_P90, width=1.3, dash="dash"),
        hovertemplate=_hover_pct("P90"),
    ))
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["Min"], mode="lines", name="Mínimo histórico",
        line=dict(color=COLOR_MIN_HIST, width=1.3, dash="dot"),
        hovertemplate=_hover_pct("Mínimo histórico"),
    ))
    fig.add_trace(go.Scatter(
        x=bands["HydroDay"], y=bands["P50"], mode="lines", name="Mediana",
        line=dict(color=COLOR_MEDIANA, width=1.3, dash="dash"),
        hovertemplate=_hover_pct("Mediana"),
    ))
    # --- Volumen útil (meses cerrados) ---
    closed = current_split["closed_months"]
    if len(closed):
        fig.add_trace(go.Scatter(
            x=closed["HydroDay"], y=closed["value"], mode="lines+markers",
            name="Volumen útil",
            line=dict(color=COLOR_ACTUAL, width=2.5),
            marker=dict(symbol="diamond", size=8, color=COLOR_ACTUAL),
            hovertemplate=_hover_pct("Volumen útil"),
        ))
        _add_pct_labels(fig, closed["HydroDay"], closed["value"])

    # --- Volumen útil mes actual (punto aislado) ---
    current_pt = current_split["current_point"]
    if len(current_pt):
        fig.add_trace(go.Scatter(
            x=current_pt["HydroDay"], y=current_pt["value"], mode="markers",
            name="Volumen útil Mes Actual",
            marker=dict(symbol="diamond", size=9, color=COLOR_ACTUAL,
                        line=dict(color="white", width=1)),
            hovertemplate=_hover_pct("Volumen útil Mes Actual"),
        ))
        _add_pct_labels(fig, current_pt["HydroDay"], current_pt["value"])

    fig.update_layout(
        font=dict(family=FONT_FAMILY, color="#1a1a2e"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=430,
        margin=dict(l=50, r=20, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, x=0.5, xanchor="center",
                    font=dict(size=10, family=FONT_FAMILY)),
        hovermode="x unified",
    )
    fig.update_yaxes(
        title="% de reservas", range=[28, 92], ticksuffix=" %",
        gridcolor="#ececec", zeroline=False,
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=labels["hydro_day"],
        ticktext=labels["label"],
        gridcolor="#f5f5f5",
    )
    return fig


COLOR_COND_FILL = "rgba(46, 46, 143, 0.18)"   # tinte del Azul Icesi oscuro
COLOR_COND_LINE = ICESI_BLUE_DARK


def add_conditional_band(fig: go.Figure, cond_bands, anchor_label: str = "") -> go.Figure:
    """Superpone la banda P10-P90 CONDICIONADA por ENSO (Etapa 2) sobre una
    figura ya construida con build_reservas_figure(). Usa un azul MÁS
    OSCURO de la misma familia (no un color ajeno como morado) para que se
    lea como "la misma marca, un escenario más específico" en vez de un
    elemento visualmente desconectado."""
    name_suffix = f" ({anchor_label})" if anchor_label else ""

    # P90/P10 condicionados: antes eran invisibles y sin hover (solo
    # existían para armar el relleno) — la banda sombreada se veía pero no
    # se podía leer ningún número. Se les deja `showlegend=False` (el
    # relleno ya se distingue a simple vista y no hace falta duplicar
    # entradas de leyenda), pero SÍ hover, para que el rango de
    # incertidumbre del pronóstico se pueda leer, no solo estimar a ojo.
    p90_cond_name = f"P90 condicionado (ENSO){name_suffix}"
    p10_cond_name = f"P10 condicionado (ENSO){name_suffix}"
    fig.add_trace(go.Scatter(
        x=cond_bands["HydroDay"], y=cond_bands["P90_cond"], mode="lines",
        name=p90_cond_name,
        line=dict(width=0), showlegend=False,
        hovertemplate=_hover_pct(p90_cond_name),
    ))
    fig.add_trace(go.Scatter(
        x=cond_bands["HydroDay"], y=cond_bands["P10_cond"], mode="lines",
        name=p10_cond_name,
        line=dict(width=0), fill="tonexty", fillcolor=COLOR_COND_FILL,
        showlegend=False,
        hovertemplate=_hover_pct(p10_cond_name),
    ))
    cond_name = f"Mediana condicionada ENSO{name_suffix}"
    fig.add_trace(go.Scatter(
        x=cond_bands["HydroDay"], y=cond_bands["P50_cond"], mode="lines",
        name=cond_name,
        line=dict(color=COLOR_COND_LINE, width=2, dash="dashdot"),
        hovertemplate=_hover_pct(cond_name),
    ))
    return fig
