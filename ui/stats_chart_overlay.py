"""
stats_chart_overlay.py — Dialog de visualisation graphique (matplotlib)

Deux modes :
  overlay.show_doc_evolution(entry: DocStatEntry)
      → courbe linéaire dates × mots, droite de tendance si baseline connue

  overlay.show_custom_stat(entry: CustomStatEntry)
      → bar / line / pie selon entry.chart_type
"""

import logging
from datetime import datetime

import matplotlib
matplotlib.use("QtAgg")  # backend Qt sans fenêtre indépendante
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from core.stats_engine import CustomStatEntry, DocStatEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette dark
# ---------------------------------------------------------------------------
_BG = "#1e1e1e"
_FG = "#cccccc"
_ACCENT = "#e0a020"
_GRID = "#3a3a3a"
_LINE = "#e0a020"
_BAR = "#4e8fd4"
_PIE_COLORS = ["#4e8fd4", "#e0a020", "#5cb85c", "#c94f4f", "#9b59b6",
               "#1abc9c", "#e67e22", "#3498db", "#e74c3c", "#2ecc71"]

_OVERLAY_STYLE = """
QDialog#StatsChartOverlay {
    background-color: #1e1e1e;
}
QLabel#ChartTitle {
    color: #e0a020;
    font-size: 15px;
    font-weight: bold;
    padding: 12px 16px 4px 16px;
}
QLabel#ChartDesc {
    color: #888888;
    font-size: 12px;
    padding: 0 16px 8px 16px;
}
QPushButton#CloseBtn {
    background: transparent;
    color: #888888;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 12px;
}
QPushButton#CloseBtn:hover {
    color: #cccccc;
    border-color: #666666;
}
"""


def _apply_dark_style(fig: Figure, ax) -> None:
    """Applique le thème dark à une figure matplotlib."""
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_FG, labelsize=9)
    ax.xaxis.label.set_color(_FG)
    ax.yaxis.label.set_color(_FG)
    ax.title.set_color(_FG)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    ax.grid(True, color=_GRID, linewidth=0.5, linestyle="--", alpha=0.7)


class StatsChartOverlay(QDialog):
    """Dialog modal affichant un graphique matplotlib."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsChartOverlay")
        self.setWindowTitle("Statistiques")
        self.setMinimumSize(680, 480)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_OVERLAY_STYLE)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        self._title_label = QLabel("")
        self._title_label.setObjectName("ChartTitle")
        layout.addWidget(self._title_label)

        self._desc_label = QLabel("")
        self._desc_label.setObjectName("ChartDesc")
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        # Zone canvas matplotlib
        self._canvas_container = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(12, 0, 12, 0)
        layout.addWidget(self._canvas_container, stretch=1)

        # Bouton fermer
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 0, 16, 0)
        btn_row.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setObjectName("CloseBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _clear_canvas(self) -> None:
        """Supprime l'ancien canvas s'il existe."""
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        plt.close("all")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def show_doc_evolution(self, entry: DocStatEntry) -> None:
        """Affiche la courbe d'évolution du nombre de mots d'un document."""
        self._clear_canvas()
        self._title_label.setText(f"Evolution — {entry.title}")

        if not entry.injections:
            self._desc_label.setText("Aucune donnée d'injection disponible.")
            return

        injections = sorted(entry.injections, key=lambda i: i.date)
        dates = [datetime.strptime(i.date, "%Y-%m-%d") for i in injections]
        words = [i.word_count for i in injections]

        delta_txt = ""
        if entry.word_count_delta is not None:
            sign = "+" if entry.word_count_delta >= 0 else ""
            delta_txt = f"  |  Évolution : {sign}{entry.word_count_delta:,} mots depuis la session précédente"

        baseline_txt = ""
        if entry.baseline_wpd:
            baseline_txt = f"  |  Objectif : {entry.baseline_wpd} mots/jour"

        self._desc_label.setText(
            f"{len(injections)} injection(s)  |  Dernier relevé : {words[-1]:,} mots"
            + delta_txt + baseline_txt
        )

        fig = Figure(figsize=(8, 4.2), tight_layout=True)
        ax = fig.add_subplot(111)
        _apply_dark_style(fig, ax)

        # Courbe principale
        ax.plot(dates, words, color=_LINE, linewidth=2, marker="o",
                markersize=6, markerfacecolor=_ACCENT, zorder=3, label="Mots")
        ax.fill_between(dates, words, alpha=0.12, color=_LINE)

        # Droite de tendance si baseline connue et > 1 point
        if entry.baseline_wpd and len(dates) > 1:
            start_count = words[0]
            from_date = dates[0]
            trend_words = [
                start_count + entry.baseline_wpd * (d - from_date).days
                for d in dates
            ]
            ax.plot(dates, trend_words, color="#888888", linewidth=1,
                    linestyle="--", label=f"Objectif ({entry.baseline_wpd} mots/j)")

        # Formatage de l'axe X
        if len(dates) == 1:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %Y"))
        elif (dates[-1] - dates[0]).days <= 60:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, (dates[-1] - dates[0]).days // 8)))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
            ax.xaxis.set_major_locator(mdates.MonthLocator())

        fig.autofmt_xdate(rotation=30, ha="right")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
        ax.set_ylabel("Nombre de mots", color=_FG, fontsize=10)
        ax.set_xlabel("Date", color=_FG, fontsize=10)

        if entry.baseline_wpd:
            ax.legend(facecolor="#2d2d2d", edgecolor=_GRID, labelcolor=_FG, fontsize=9)

        canvas = FigureCanvasQTAgg(fig)
        self._canvas_layout.addWidget(canvas)

    def show_custom_stat(self, entry: CustomStatEntry) -> None:
        """Affiche le graphique correspondant à une stat personnalisée."""
        self._clear_canvas()
        self._title_label.setText(entry.name)
        self._desc_label.setText(entry.description or "Stat personnalisée")

        labels = entry.data.get("labels", [])
        values = entry.data.get("values", [])
        colors = entry.data.get("colors", None)

        if not labels or not values:
            self._desc_label.setText("Données insuffisantes pour tracer un graphique.")
            return

        fig = Figure(figsize=(8, 4.2), tight_layout=True)

        if entry.chart_type == "pie":
            ax = fig.add_subplot(111)
            fig.patch.set_facecolor(_BG)
            ax.set_facecolor(_BG)
            pie_colors = colors if colors else _PIE_COLORS[:len(labels)]
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                colors=pie_colors,
                autopct="%1.1f%%",
                startangle=140,
                pctdistance=0.82,
                wedgeprops={"edgecolor": _BG, "linewidth": 2},
            )
            for t in texts:
                t.set_color(_FG)
                t.set_fontsize(10)
            for at in autotexts:
                at.set_color(_BG)
                at.set_fontweight("bold")
                at.set_fontsize(9)

        elif entry.chart_type == "line":
            ax = fig.add_subplot(111)
            _apply_dark_style(fig, ax)
            bar_colors = colors if colors else [_LINE] * len(values)
            ax.plot(labels, values, color=_LINE, linewidth=2, marker="o",
                    markersize=6, markerfacecolor=_ACCENT)
            ax.fill_between(range(len(values)), values, alpha=0.12, color=_LINE)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
            ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))

        else:  # bar (défaut)
            ax = fig.add_subplot(111)
            _apply_dark_style(fig, ax)
            bar_colors = colors if colors else [_BAR] * len(values)
            bars = ax.bar(labels, values, color=bar_colors, edgecolor=_BG,
                          linewidth=0.8, zorder=3)
            # Valeurs au-dessus des barres
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    str(val),
                    ha="center", va="bottom",
                    color=_FG, fontsize=9,
                )
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
            ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))

        canvas = FigureCanvasQTAgg(fig)
        self._canvas_layout.addWidget(canvas)
