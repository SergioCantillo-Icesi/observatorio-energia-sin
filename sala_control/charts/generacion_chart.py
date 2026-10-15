"""
charts/generacion_chart.py — Barras apiladas de generación por tecnología y
hora, para la "Matriz de Generación Horaria".

Paleta: variantes de Azul Icesi (igual que reservas_chart.py) para las
tecnologías "en familia" con la identidad institucional, y colores
semánticos estándar de la industria SOLO donde ayudan a reconocer de un
vistazo la tecnología (amarillo=solar, verde=eólica) — mezclar 6 tonos de
un solo azul haría el gráfico casi ilegible por contraste insuficiente
entre categorías, así que aquí se prioriza la función semántica sobre la
paleta pura de marca (a diferencia del gráfico de reservas, que sí es
100% familia de azules).
"""
from __future__ import annotations

import plotly.graph_objects as go

from sala_control.analytics.generacion_mix import ORDEN_TIPOS
from sala_control.theme import ICESI_BLUE, ICESI_BLUE_DARK, ICESI_GRAY, FONT_FAMILY

COLORES = {
    "Hidráulica": ICESI_BLUE,
    "Térmica": "#B23A48",
    "FNCER": "#4CA37A",
    "Otra centralizada": ICESI_GRAY,
    "Gen. Distribuida (GD)": ICESI_BLUE_DARK,
    "Autogeneración (AUTOG)": "#8E8EF0",
}


def build_generacion_figure(gen_por_tipo, etiquetas_leyenda: dict[str, str] | None = None) -> go.Figure:
    """gen_por_tipo: DataFrame indexado por 'Tipo', columnas H1..H24 (salida
    de analytics.generacion_mix.compute_gen_por_tipo).

    `etiquetas_leyenda`: dict opcional {Tipo: etiqueta enriquecida} — salida
    de analytics.generacion_mix.etiquetas_leyenda_con_fuente(), para que la
    leyenda muestre el tipo de energía real detrás de cada categoría (ej.
    'Térmica (Carbón, Gas Natural)' en vez de solo 'Térmica').

    Sin título interno: el nombre de la pestaña que contiene el gráfico
    (ej. "📊 Generación por hora") ya cumple esa función."""
    horas = list(range(1, len(gen_por_tipo.columns) + 1))
    etiquetas_leyenda = etiquetas_leyenda or {}

    fig = go.Figure()
    for tipo in ORDEN_TIPOS:
        if tipo not in gen_por_tipo.index:
            continue
        fig.add_trace(go.Bar(
            x=horas, y=gen_por_tipo.loc[tipo], name=etiquetas_leyenda.get(tipo, tipo),
            marker_color=COLORES.get(tipo, ICESI_GRAY),
            customdata=[tipo] * len(horas),
            hovertemplate="<b>%{customdata}</b>: %{y:.2f} MWh<extra></extra>",
        ))

    fig.update_layout(
        font=dict(family=FONT_FAMILY, color="#1a1a2e"),
        xaxis=dict(title="Hora del día", tickmode="linear", tick0=1, dtick=1),
        yaxis=dict(title="Generación (MWh)", tickformat=".0f", rangemode="nonnegative"),
        barmode="stack",
        # Horizontal, pero forzando 1 categoría por fila: entrywidth=1
        # (fraction) hace que cada entrada ocupe el 100% del ancho
        # disponible, así nunca cabe una segunda al lado y Plotly no puede
        # "acomodarlas" en una grilla de columnas desalineada — cada fila
        # es exactamente una categoría, de arriba a abajo.
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center",
                    entrywidth=1, entrywidthmode="fraction",
                    font=dict(size=10, family=FONT_FAMILY), traceorder="normal"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=460,
        margin=dict(t=20, b=140, r=20, l=50),
        hovermode="x unified",
    )
    return fig


def build_participacion_barchart(df_part, color: str = ICESI_BLUE) -> go.Figure:
    """Barras horizontales compactas para % de participación (tecnología o
    agente) — reemplaza una tabla plana por algo más legible de un vistazo,
    sin ocupar mucho espacio vertical: la altura se ajusta automáticamente
    al número de categorías (no un tamaño fijo que desperdicia o se queda
    corto de espacio), y las etiquetas van directo sobre cada barra en vez
    de exigir leer un eje.

    `df_part`: DataFrame de una sola columna 'Participación (%)', índice =
    nombre de la categoría/agente (salida de generacion_mix.resumen_participacion
    o resumen_participacion_agente). Se asume ya viene ordenado."""
    if len(df_part) == 0:
        fig = go.Figure()
        fig.update_layout(
            height=80, margin=dict(t=10, b=10, l=10, r=10),
            annotations=[dict(text="Sin datos", showarrow=False,
                               font=dict(family=FONT_FAMILY, color=ICESI_GRAY))],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        return fig

    valores = df_part.iloc[:, 0]
    etiquetas = valores.index.tolist()

    fig = go.Figure(go.Bar(
        x=valores.values,
        y=etiquetas,
        orientation="h",
        marker_color=color,
        text=[f"{v:.1f} %" for v in valores.values],
        textposition="outside",
        hovertemplate="<b>%{y}</b>: %{x:.1f} %<extra></extra>",
    ))

    # Altura proporcional al número de filas — compacto con pocas
    # categorías, nunca apretado con muchas (ej. muchos agentes).
    altura = max(90, 30 * len(etiquetas) + 40)

    fig.update_layout(
        font=dict(family=FONT_FAMILY, color="#1a1a2e"),
        xaxis=dict(visible=False, range=[0, max(valores.values) * 1.25]),
        yaxis=dict(autorange="reversed", showgrid=False),  # el % más alto arriba
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=altura,
        margin=dict(t=16, b=6, l=6, r=40),
        showlegend=False,
    )
    return fig
