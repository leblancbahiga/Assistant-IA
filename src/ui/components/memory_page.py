"""
Memory Page — Affichage des Faits, Cache Sémantique et Procédures.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QScrollArea, QPushButton, QLineEdit,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QComboBox, QMessageBox)
from PySide6.QtCore import Qt, QTimer
import logging
import os

logger = logging.getLogger(__name__)


class MemoryPage(QWidget):
    def __init__(self, memory_store=None, parent=None):
        super().__init__(parent)
        self.memory_store = memory_store
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15000)  # 15 s auto-refresh
        self._refresh_timer.timeout.connect(self._refresh_data)
        self.setup_ui()
        # Start auto-refresh once UI is built
        self._refresh_timer.start()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("🧠  MÉMOIRE")
        title.setObjectName("PageTitle")

        self.btn_purge = QPushButton("🗑  Purger")
        self.btn_purge.setObjectName("GhostButton")
        self.btn_purge.setCursor(Qt.PointingHandCursor)
        self.btn_purge.clicked.connect(self._purge_cache)

        self.btn_analyze = QPushButton("📊  Analyser")
        self.btn_analyze.setObjectName("GhostButton")
        self.btn_analyze.setCursor(Qt.PointingHandCursor)
        self.btn_analyze.clicked.connect(self._analyze_memory)

        btn_refresh = QPushButton("↻  Actualiser")
        btn_refresh.setObjectName("GhostButton")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh_data)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_purge)
        header.addWidget(self.btn_analyze)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stat_facts = self._make_stat_card("📌 Faits Stockés", "0")
        self.stat_cache = self._make_stat_card("💾 Cache Sémantique", "0 entrées")
        self.stat_procedures = self._make_stat_card("📋 Procédures", "0 règles")
        stats_row.addWidget(self.stat_facts)
        stats_row.addWidget(self.stat_cache)
        stats_row.addWidget(self.stat_procedures)
        layout.addLayout(stats_row)

        # Info / status label (for guidance when memory_store is None or empty)
        self.status_label = QLabel("")
        self.status_label.setObjectName("MemoryStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color: #9CA3AF; font-size: 12px; padding: 4px 8px;"
            " background: rgba(255,255,255,0.03); border-radius: 4px;"
        )
        self.status_label.hide()
        layout.addWidget(self.status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)

        # === FAITS ===
        facts_panel = QFrame()
        facts_panel.setObjectName("Panel")
        facts_layout = QVBoxLayout(facts_panel)

        facts_header = QHBoxLayout()
        facts_title = QLabel("📌  FAITS MÉMORISÉS")
        facts_title.setObjectName("PanelTitle")
        facts_header.addWidget(facts_title)
        facts_header.addStretch()
        facts_layout.addLayout(facts_header)

        # Add fact
        add_row = QHBoxLayout()
        self.fact_input = QLineEdit()
        self.fact_input.setObjectName("ChatInput")
        self.fact_input.setPlaceholderText("Ajouter un fait...")
        self.fact_category = QComboBox()
        self.fact_category.setObjectName("StyledCombo")
        self.fact_category.addItems(["general", "professional", "personal", "technical"])
        btn_add = QPushButton("+ Ajouter")
        btn_add.setObjectName("PrimaryButton")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._add_fact)
        add_row.addWidget(self.fact_input, stretch=1)
        add_row.addWidget(self.fact_category)
        add_row.addWidget(btn_add)
        facts_layout.addLayout(add_row)

        self.facts_table = QTableWidget()
        self.facts_table.setObjectName("DataTable")
        self.facts_table.setColumnCount(3)
        self.facts_table.setHorizontalHeaderLabels(["Contenu", "Catégorie", "Date"])
        self.facts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.facts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.facts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.facts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.facts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        facts_layout.addWidget(self.facts_table)

        # Empty-state label inside the facts panel (shown when table is empty)
        self.facts_empty_label = QLabel("Aucun fait mémorisé pour le moment.")
        self.facts_empty_label.setAlignment(Qt.AlignCenter)
        self.facts_empty_label.setStyleSheet(
            "color: #9CA3AF; font-size: 13px; padding: 20px;"
        )
        self.facts_empty_label.hide()
        facts_layout.addWidget(self.facts_empty_label)

        content_layout.addWidget(facts_panel)

        # === PROCÉDURES ===
        proc_panel = QFrame()
        proc_panel.setObjectName("Panel")
        proc_layout = QVBoxLayout(proc_panel)
        proc_title = QLabel("📋  PROCÉDURES & RÈGLES")
        proc_title.setObjectName("PanelTitle")
        proc_layout.addWidget(proc_title)

        self.proc_label = QLabel("Aucune procédure enregistrée.")
        self.proc_label.setWordWrap(True)
        self.proc_label.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 10px;")
        proc_layout.addWidget(self.proc_label)
        content_layout.addWidget(proc_panel)

        # === FALLBACK INFO PANEL (shown when memory_store is None) ===
        self.fallback_panel = QFrame()
        self.fallback_panel.setObjectName("Panel")
        fallback_layout = QVBoxLayout(self.fallback_panel)
        fallback_title = QLabel("ℹ️  STOCK DE MÉMOIRE NON DISPONIBLE")
        fallback_title.setObjectName("PanelTitle")
        fallback_layout.addWidget(fallback_title)

        self.fallback_text = QLabel(
            "Le module MemoryStore n'est pas connecté.\n\n"
            "Cela peut arriver si :\n"
            "  • La base de données n'a pas encore été initialisée\n"
            "  • L'import de MemoryStore a échoué (dépendances manquantes)\n"
            "  • Aucun core NURU n'a fourni de store mémoire\n\n"
            "Vous pouvez :\n"
            "  • Redémarrer le dashboard après installation complète\n"
            "  • Vérifier les logs dans la page 📋 Logs\n"
            "  • Revenir plus tard quand le système sera prêt\n\n"
            "Dès qu'un MemoryStore sera disponible, cette page s'affichera "
            "automatiquement."
        )
        self.fallback_text.setWordWrap(True)
        self.fallback_text.setStyleSheet(
            "color: #9CA3AF; font-size: 13px; padding: 10px; line-height: 1.6;"
        )
        fallback_layout.addWidget(self.fallback_text)
        self.fallback_panel.hide()
        content_layout.addWidget(self.fallback_panel)

        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

    def _make_stat_card(self, title, value):
        frame = QFrame()
        frame.setObjectName("Panel")
        frame.setFixedHeight(65)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(15, 8, 15, 8)
        t = QLabel(title)
        t.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 600;")
        v = QLabel(value)
        v.setObjectName(f"stat_value_{title}")
        v.setStyleSheet("color: #F3F4F6; font-size: 18px; font-weight: bold;")
        fl.addWidget(t)
        fl.addWidget(v)
        frame._value_label = v
        return frame

    # ─────────────────────────────────────────────────────────
    #  _refresh_data() — Central data-loading method
    # ─────────────────────────────────────────────────────────
    def _refresh_data(self):
        """Check memory_store availability and refresh all displayed data.

        Handles three scenarios:
          1. memory_store is None → show fallback guidance panel
          2. memory_store exists → show live data (or empty-state with info)
          3. errors during load → show user-friendly message with fallback info
        """
        if self.memory_store is None:
            self._show_no_store_state()
            return

        try:
            self._load_from_store()
        except Exception as e:
            logger.warning("MemoryPage._refresh_data error: %s", e)
            self._show_error_state(e)

    def _show_no_store_state(self):
        """Display the fallback panel explaining memory_store is unavailable."""
        self.fallback_panel.show()
        self.status_label.hide()
        self.facts_table.setRowCount(0)
        self.facts_empty_label.hide()
        self.proc_label.setText("Aucune procédure enregistrée.")

        self.stat_facts._value_label.setText("—")
        self.stat_cache._value_label.setText("—")
        self.stat_procedures._value_label.setText("—")

        # Disable action buttons that require memory_store
        self.btn_purge.setEnabled(False)
        self.btn_analyze.setEnabled(False)

    def _show_error_state(self, error: Exception):
        """Display partial data with an error message."""
        self.fallback_panel.hide()
        self.status_label.show()
        self.status_label.setText(
            f"⚠️ Erreur lors du chargement : {error}\n"
            "Les données affichées peuvent être incomplètes."
        )
        self.btn_purge.setEnabled(True)
        self.btn_analyze.setEnabled(True)

        # Try to show whatever we can
        try:
            self._populate_facts_table()
        except Exception:
            pass
        try:
            self._populate_procedures()
        except Exception:
            pass
        self._update_stats_from_store()

    def _load_from_store(self):
        """Load data from memory_store and update all widgets."""
        self.fallback_panel.hide()
        self.status_label.hide()
        self.btn_purge.setEnabled(True)
        self.btn_analyze.setEnabled(True)

        # Fill facts table
        self._populate_facts_table()

        # Fill procedures
        self._populate_procedures()

        # Update stat cards from store
        self._update_stats_from_store()

    def _populate_facts_table(self):
        """Populate the facts table with data from memory_store, or show empty state."""
        if self.memory_store is None:
            return

        facts = self.memory_store.get_recent_facts(limit=50)
        user_facts = self.memory_store.get_user_facts(limit=50)

        total_rows = len(facts) + len(user_facts)

        if total_rows == 0:
            # Show empty-state guidance with DB info
            self.facts_table.setRowCount(0)
            self.facts_empty_label.show()
            db_info = self._get_db_info()
            self.facts_empty_label.setText(
                "🧠  Aucun fait mémorisé pour le moment.\n\n"
                "Ajoutez un fait ci-dessus ou attendez que NURU "
                "mémorise des informations au fil des conversations.\n\n"
                f"{db_info}"
            )
            return

        self.facts_empty_label.hide()
        self.facts_table.setRowCount(total_rows)

        for i, fact in enumerate(facts):
            self.facts_table.setItem(i, 0, QTableWidgetItem(fact))
            self.facts_table.setItem(i, 1, QTableWidgetItem("general"))
            self.facts_table.setItem(i, 2, QTableWidgetItem("—"))

        for j, uf in enumerate(user_facts):
            row = len(facts) + j
            self.facts_table.setItem(
                row, 0,
                QTableWidgetItem(f"[{uf['fact_type']}] {uf['content']}")
            )
            self.facts_table.setItem(row, 1, QTableWidgetItem(uf['fact_type']))
            self.facts_table.setItem(
                row, 2,
                QTableWidgetItem(
                    uf.get('updated_at', '—')[:10]
                    if uf.get('updated_at') else '—'
                )
            )

    def _populate_procedures(self):
        """Populate the procedures section from memory_store."""
        if self.memory_store is None:
            self.proc_label.setText("Aucune procédure enregistrée.")
            return

        procedures = self.memory_store.get_procedures()
        if procedures and procedures.strip():
            self.proc_label.setText(procedures)
        else:
            self.proc_label.setText("Aucune procédure enregistrée.")

    def _update_stats_from_store(self):
        """Update stat cards with counts from memory_store."""
        if self.memory_store is None:
            return

        facts_count = self._safe_count("get_total_facts_count")
        user_facts_count = self._safe_count("get_total_user_facts_count")
        total_facts = facts_count + user_facts_count
        self.stat_facts._value_label.setText(str(total_facts))

        # Cache stats
        try:
            cache_stats = self.memory_store.get_cache_stats()
            cache_entries = cache_stats.get("total_entries", 0)
            self.stat_cache._value_label.setText(f"{cache_entries} entrées")
        except Exception:
            self.stat_cache._value_label.setText("?")

        # Procedures count
        try:
            procedures = self.memory_store.get_procedures()
            proc_count = len(procedures.split('\n')) if procedures.strip() else 0
            self.stat_procedures._value_label.setText(f"{proc_count} règles")
        except Exception:
            self.stat_procedures._value_label.setText("? règles")

    def _safe_count(self, method_name: str) -> int:
        """Call a count method on memory_store safely, returning 0 on failure."""
        try:
            method = getattr(self.memory_store, method_name, None)
            if method is not None and callable(method):
                return method()
        except Exception:
            pass
        return 0

    def _get_db_info(self) -> str:
        """Return a human-readable string about the DB path and size."""
        try:
            db_path = getattr(self.memory_store, "db_path", None)
            if db_path is not None:
                db_path_str = str(db_path)
                size_kb = 0
                try:
                    size_kb = self.memory_store.get_memory_size() / 1024
                except Exception:
                    try:
                        size_kb = os.path.getsize(db_path) / 1024
                    except Exception:
                        size_kb = 0
                return (
                    f"📁 Base : {db_path_str}\n"
                    f"💾 Taille : {size_kb:.1f} KB"
                )
        except Exception:
            pass
        return ""

    # ─────────────────────────────────────────────────────────
    #  Legacy load_data() — delegates to _refresh_data
    # ─────────────────────────────────────────────────────────
    def load_data(self):
        """Legacy entry point — delegates to _refresh_data()."""
        self._refresh_data()

    # ─────────────────────────────────────────────────────────
    #  Actions
    # ─────────────────────────────────────────────────────────
    def _add_fact(self):
        text = self.fact_input.text().strip()
        if text and self.memory_store:
            category = self.fact_category.currentText()
            self.memory_store.add_fact(text, category)
            self.fact_input.clear()
            self._refresh_data()

    def _purge_cache(self):
        if not self.memory_store:
            QMessageBox.information(
                self, "Non disponible",
                "Aucun MemoryStore connecté. Impossible de purger le cache."
            )
            return
        reply = QMessageBox.question(
            self, "Purger le cache",
            "Voulez-vous vraiment purger le cache sémantique ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.memory_store.purge_cache()
            self.stat_cache._value_label.setText("0 entrées")
            self._refresh_data()

    def _analyze_memory(self):
        if not self.memory_store:
            QMessageBox.information(
                self, "Non disponible",
                "Aucun MemoryStore connecté. Impossible d'analyser la mémoire.\n\n"
                "Vérifiez que la base de données mémoire est bien initialisée."
            )
            return
        try:
            analysis = self.memory_store.analyze_memory()
            msg = (
                f"📊 Analyse Mémoire\n\n"
                f"Faits stockés : {analysis.get('total_facts', '?')}\n"
                f"Messages historiques : {analysis.get('total_history', '?')}\n"
                f"Procédures : {analysis.get('total_procedures', '?')}\n"
                f"Réflexions : {analysis.get('total_reflections', '?')}\n"
                f"Cache entries : {analysis.get('cache_entries', '?')}\n"
                f"Cache hits : {analysis.get('cache_hits', '?')}\n"
                f"Taille DB : {analysis.get('db_size_kb', '?')} KB\n"
                f"Activité récente (1h) : {analysis.get('recent_activity', '?')} messages"
            )
            QMessageBox.information(self, "Analyse Mémoire", msg)
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Analyse impossible : {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_data()

    def closeEvent(self, event):
        """Clean up the auto-refresh timer on close."""
        self._refresh_timer.stop()
        super().closeEvent(event)
