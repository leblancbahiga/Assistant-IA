"""
Documents Page — Base documentaire avec tableau complet, recherche,
filtres, import de fichiers et débogage RAG.
"""

import os
import time
import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QMenu, QComboBox,
    QLineEdit, QTextEdit,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction


# ─────────────────────────────────────────────────────────
# IndexWorker (Thread d'indexation)
# ─────────────────────────────────────────────────────────

class IndexWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(dict)
    error = Signal(str, str)

    def __init__(self, ingestion, file_paths: list):
        super().__init__()
        self.ingestion = ingestion
        self.file_paths = file_paths

    def run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        total = len(self.file_paths)
        indexed = 0
        errors = []
        start_ts = time.time()

        for i, filepath in enumerate(self.file_paths):
            if not os.path.isfile(filepath):
                continue
            try:
                loop.run_until_complete(self.ingestion.index_file(str(filepath)))
                indexed += 1
            except Exception as e:
                errors.append((os.path.basename(filepath), str(e)))
            self.progress.emit(i + 1, total, os.path.basename(filepath))

        duration = time.time() - start_ts
        self.finished.emit({
            "total": total,
            "indexed": indexed,
            "errors": errors,
            "duration_s": round(duration, 1),
        })


# ─────────────────────────────────────────────────────────
# DocumentsPage
# ─────────────────────────────────────────────────────────

class DocumentsPage(QWidget):
    """Panneau de gestion de la base documentaire RAG."""

    SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".xlsx", ".md", ".csv", ".json"}

    def __init__(self, rag_engine=None, ingestion_engine=None, parent=None):
        super().__init__(parent)
        self.rag_engine = rag_engine
        self.ingestion = ingestion_engine
        self.index_worker = None
        self._documents_data = []  # cache local des documents
        self.setup_ui()
        self.setAcceptDrops(True)

    # ─────────── UI SETUP ───────────

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── 1. HEADER ──
        header = QHBoxLayout()
        title = QLabel("📁 BASE DOCUMENTAIRE")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        self.btn_import = QPushButton("📂 Importer")
        self.btn_import.setObjectName("PrimaryBtn")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.clicked.connect(self._on_import)

        self.btn_multi_import = QPushButton("📂 Import Multiple")
        self.btn_multi_import.setObjectName("GhostBtn")
        self.btn_multi_import.setCursor(Qt.PointingHandCursor)
        self.btn_multi_import.clicked.connect(self._on_multi_import)

        self.btn_refresh = QPushButton("↻ Actualiser")
        self.btn_refresh.setObjectName("GhostBtn")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.load_documents)

        self.btn_delete = QPushButton("🗑 Supprimer")
        self.btn_delete.setObjectName("GhostBtn")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self._delete_selected)

        header.addWidget(self.btn_import)
        header.addWidget(self.btn_multi_import)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.btn_delete)
        layout.addLayout(header)

        # ── 2. FILTERS BAR ──
        filters_frame = QFrame()
        filters_frame.setObjectName("FilterBar")
        filters_frame.setFixedHeight(44)
        filters_layout = QHBoxLayout(filters_frame)
        filters_layout.setContentsMargins(12, 4, 12, 4)
        filters_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Rechercher un document…")
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setClearButtonEnabled(True)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName("TypeFilter")
        self.type_filter.addItems(["Tous", "PDF", "DOCX", "TXT", "XLSX", "MD"])
        self.type_filter.currentTextChanged.connect(self._on_type_filter)

        self.date_filter = QComboBox()
        self.date_filter.setObjectName("DateFilter")
        self.date_filter.addItems(["Toutes dates", "Aujourd'hui", "7 jours", "30 jours", "90 jours"])
        self.date_filter.currentTextChanged.connect(self._on_date_filter)

        self.sort_by = QComboBox()
        self.sort_by.setObjectName("SortBy")
        self.sort_by.addItems(["Nom", "Date", "Taille", "Nombre chunks"])
        self.sort_by.currentTextChanged.connect(self._on_sort_changed)

        filters_layout.addWidget(self.search_input, stretch=1)
        filters_layout.addWidget(QLabel("Type:"))
        filters_layout.addWidget(self.type_filter)
        filters_layout.addWidget(QLabel("Période:"))
        filters_layout.addWidget(self.date_filter)
        filters_layout.addWidget(QLabel("Trier:"))
        filters_layout.addWidget(self.sort_by)
        layout.addWidget(filters_frame)

        # ── 3. STATS BAR ──
        stats_frame = QFrame()
        stats_frame.setObjectName("Panel")
        stats_frame.setFixedHeight(46)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 6, 15, 6)
        stats_layout.setSpacing(20)

        self.lbl_doc_count = QLabel("📄 Documents: 0")
        self.lbl_doc_count.setObjectName("DocCount")
        self.lbl_chunk_count = QLabel("🧩 Chunks: 0")
        self.lbl_chunk_count.setObjectName("ChunkCount")
        self.lbl_last_index = QLabel("📅 Dernière indexation: —")
        self.lbl_last_index.setObjectName("LastIndexDate")

        stats_layout.addWidget(self.lbl_doc_count)
        stats_layout.addWidget(self.lbl_chunk_count)
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_last_index)
        layout.addWidget(stats_frame)

        # ── 4. PROGRESS BAR (hidden by default) ──
        self.index_progress = QProgressBar()
        self.index_progress.setObjectName("IndexProgress")
        self.index_progress.setFixedHeight(6)
        self.index_progress.setTextVisible(False)
        self.index_progress.setVisible(False)
        layout.addWidget(self.index_progress)

        self.index_status = QLabel()
        self.index_status.setObjectName("IndexStatus")
        self.index_status.setVisible(False)
        layout.addWidget(self.index_status)

        # ── 5. TABLE ──
        self.table = QTableWidget()
        self.table.setObjectName("DocTable")
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Nom", "Type", "Taille", "Pages", "Chunks",
            "Date import", "Statut"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, stretch=1)

        # ── 6. EMPTY STATE ──
        self.empty_label = QLabel(
            "📂 Aucun document dans la base\n"
            "Importez des fichiers PDF, DOCX, TXT, XLSX ou MD\n"
            "via le bouton « Importer » ci-dessus."
        )
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)

        # ── 7. RAG DEBUG PANEL (collapsible) ──
        self.debug_panel = QFrame()
        self.debug_panel.setObjectName("RagDebugPanel")
        self.debug_panel.setVisible(False)
        debug_layout = QVBoxLayout(self.debug_panel)
        debug_layout.setContentsMargins(14, 10, 14, 10)
        debug_layout.setSpacing(8)

        # Header toggle
        debug_header = QHBoxLayout()
        self.debug_title = QLabel("🔍 DÉBOGAGE RAG")
        self.debug_title.setObjectName("PanelTitle")
        debug_header.addWidget(self.debug_title)
        debug_header.addStretch()
        self.toggle_debug_btn = QPushButton("🔍 Déboguer")
        self.toggle_debug_btn.setObjectName("GhostBtn")
        self.toggle_debug_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_debug_btn.setCheckable(True)
        self.toggle_debug_btn.toggled.connect(self._toggle_debug_panel)
        debug_header.addWidget(self.toggle_debug_btn)
        debug_layout.addLayout(debug_header)

        # Query line
        query_row = QHBoxLayout()
        self.debug_query_input = QLineEdit()
        self.debug_query_input.setObjectName("DebugQueryInput")
        self.debug_query_input.setPlaceholderText("Tapez une question pour voir les chunks…")
        self.debug_query_input.returnPressed.connect(self._on_debug_search)
        query_row.addWidget(self.debug_query_input, stretch=1)

        self.debug_search_btn = QPushButton("🔍")
        self.debug_search_btn.setObjectName("DebugSearchBtn")
        self.debug_search_btn.setCursor(Qt.PointingHandCursor)
        self.debug_search_btn.clicked.connect(self._on_debug_search)
        query_row.addWidget(self.debug_search_btn)
        debug_layout.addLayout(query_row)

        # Results
        results_grid = QHBoxLayout()
        results_grid.setSpacing(16)
        self.lbl_debug_docs = QLabel("Documents retrouvés: —")
        self.lbl_debug_docs.setObjectName("DebugDocFound")
        self.lbl_debug_chunks = QLabel("Chunks sélectionnés: —")
        self.lbl_debug_chunks.setObjectName("DebugChunksSelected")
        self.lbl_debug_score = QLabel("Score similarité: —")
        self.lbl_debug_score.setObjectName("DebugSimilarityScore")
        self.lbl_debug_time = QLabel("Temps: —")
        self.lbl_debug_time.setObjectName("DebugRetrievalTime")
        results_grid.addWidget(self.lbl_debug_docs)
        results_grid.addWidget(self.lbl_debug_chunks)
        results_grid.addWidget(self.lbl_debug_score)
        results_grid.addStretch()
        results_grid.addWidget(self.lbl_debug_time)
        debug_layout.addLayout(results_grid)

        self.debug_context = QTextEdit()
        self.debug_context.setObjectName("DebugSentContext")
        self.debug_context.setReadOnly(True)
        self.debug_context.setFixedHeight(180)
        debug_layout.addWidget(self.debug_context)

        layout.addWidget(self.debug_panel)

    # ─────────── LOAD DOCUMENTS ───────────

    def load_documents(self):
        """Charge la liste des documents depuis la base RAG et met à jour le tableau."""
        if not self.rag_engine:
            self.empty_label.setText("⚠ Moteur RAG non connecté — impossible de charger les documents.")
            self.empty_label.setVisible(True)
            self.table.setVisible(False)
            self.update_stats()
            return

        try:
            conn = self.rag_engine._get_conn()
            rows = conn.execute(
                "SELECT filepath, mtime, hash FROM indexed_files ORDER BY mtime DESC"
            ).fetchall()

            # Agrégation du nombre de chunks par source
            chunk_counts = {}
            try:
                cc_rows = conn.execute(
                    "SELECT source, COUNT(*) as cnt FROM chunks GROUP BY source"
                ).fetchall()
                chunk_counts = {r[0]: r[1] for r in cc_rows}
            except Exception:
                pass  # table peut être vide

            conn.close()
        except Exception as e:
            self.empty_label.setText(f"❌ Erreur de lecture de la base: {e}")
            self.empty_label.setVisible(True)
            self.table.setVisible(False)
            self.update_stats()
            return

        self._documents_data = []
        for filepath, mtime, file_hash in rows:
            name = os.path.basename(filepath)
            ext = Path(filepath).suffix.lower()
            ext_upper = ext.lstrip(".").upper() if ext else "—"
            size_bytes = 0
            size_str = "—"
            try:
                size_bytes = os.path.getsize(filepath)
                size_str = self._format_size(size_bytes)
            except OSError:
                size_str = "⚠ introuvable"
            pages = "—"
            # Estimation pages pour PDF
            if ext == ".pdf":
                try:
                    import fitz
                    doc = fitz.open(filepath)
                    pages = str(doc.page_count)
                    doc.close()
                except Exception:
                    pages = "?"
            chunks = chunk_counts.get(name, 0)
            date_str = ""
            if mtime:
                dt = datetime.datetime.fromtimestamp(mtime)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            status = "✅ Indexé" if chunks > 0 else "⏳ En attente"

            self._documents_data.append({
                "name": name,
                "ext": ext,
                "ext_upper": ext_upper,
                "size_bytes": size_bytes,
                "size_str": size_str,
                "pages": pages,
                "chunks": chunks,
                "date_ts": mtime or 0,
                "date_str": date_str,
                "status": status,
                "filepath": filepath,
                "hash": file_hash,
            })

        self._apply_filters_and_sort()
        self.update_stats()

    def _apply_filters_and_sort(self):
        """Applique la recherche, les filtres et le tri actifs, puis remplit le tableau."""
        data = self._documents_data[:]

        # ── Texte ──
        query = self.search_input.text().strip().lower()
        if query:
            data = [d for d in data if query in d["name"].lower() or query in d["filepath"].lower()]

        # ── Type ──
        type_val = self.type_filter.currentText()
        if type_val != "Tous":
            target_ext = f".{type_val.lower()}"
            data = [d for d in data if d["ext"] == target_ext]

        # ── Date ──
        date_val = self.date_filter.currentText()
        if date_val != "Toutes dates":
            now = time.time()
            if date_val == "Aujourd'hui":
                cutoff = now - 86400
            elif date_val == "7 jours":
                cutoff = now - 7 * 86400
            elif date_val == "30 jours":
                cutoff = now - 30 * 86400
            elif date_val == "90 jours":
                cutoff = now - 90 * 86400
            else:
                cutoff = 0
            data = [d for d in data if d["date_ts"] >= cutoff]

        # ── Tri ──
        sort_val = self.sort_by.currentText()
        reverse = True if sort_val == "Date" else False
        if sort_val == "Nom":
            data.sort(key=lambda d: d["name"].lower())
        elif sort_val == "Date":
            data.sort(key=lambda d: d["date_ts"], reverse=True)
        elif sort_val == "Taille":
            data.sort(key=lambda d: d["size_bytes"], reverse=True)
        elif sort_val == "Nombre chunks":
            data.sort(key=lambda d: d["chunks"], reverse=True)

        self._populate_table(data)

    def _populate_table(self, data: list):
        """Remplit le QTableWidget avec les données filtrées/triées."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(data))

        for i, doc in enumerate(data):
            # Nom
            name_item = QTableWidgetItem(doc["name"])
            name_item.setData(Qt.UserRole, doc["filepath"])
            self.table.setItem(i, 0, name_item)
            # Type
            ext_item = QTableWidgetItem(doc["ext_upper"])
            ext_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, ext_item)
            # Taille
            size_item = QTableWidgetItem(doc["size_str"])
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, size_item)
            # Pages
            pages_item = QTableWidgetItem(str(doc["pages"]))
            pages_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, pages_item)
            # Chunks
            chunks_item = QTableWidgetItem(str(doc["chunks"]))
            chunks_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, chunks_item)
            # Date import
            date_item = QTableWidgetItem(doc["date_str"])
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, date_item)
            # Statut
            status_item = QTableWidgetItem(doc["status"])
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, status_item)

        self.table.setSortingEnabled(True)

        visible = len(data) > 0
        self.table.setVisible(visible)
        self.empty_label.setVisible(not visible)

        if not visible and self._documents_data:
            self.empty_label.setText("🔍 Aucun document ne correspond aux filtres actuels.")
        elif not visible and not self._documents_data:
            self.empty_label.setText(
                "📂 Aucun document dans la base\n"
                "Importez des fichiers PDF, DOCX, TXT, XLSX ou MD\n"
                "via le bouton « Importer » ci-dessus."
            )

    # ─────────── STATS ───────────

    def update_stats(self):
        """Met à jour les compteurs de la barre de statistiques."""
        total_docs = len(self._documents_data)
        total_chunks = sum(d["chunks"] for d in self._documents_data)
        last_ts = max((d["date_ts"] for d in self._documents_data), default=0)

        self.lbl_doc_count.setText(f"📄 Documents: {total_docs}")
        self.lbl_chunk_count.setText(f"🧩 Chunks: {total_chunks}")
        if last_ts:
            last_str = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
            self.lbl_last_index.setText(f"📅 Dernière indexation: {last_str}")
        else:
            self.lbl_last_index.setText("📅 Dernière indexation: —")

    # ─────────── IMPORT ───────────

    def _on_import(self):
        """Import simple : un seul fichier."""
        filters = (
            "Documents supportés (*.pdf *.docx *.txt *.xlsx *.md *.csv *.json);;"
            "PDF (*.pdf);;Word (*.docx);;Texte (*.txt);;Excel (*.xlsx);;"
            "Markdown (*.md);;CSV (*.csv);;JSON (*.json);;Tous (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Importer un document", "", filters)
        if path:
            self._start_indexing([path])

    def _on_multi_import(self):
        """Import multiple : sélection de plusieurs fichiers."""
        filters = (
            "Documents supportés (*.pdf *.docx *.txt *.xlsx *.md *.csv *.json);;"
            "Tous (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "Importer plusieurs documents", "", filters)
        if paths:
            self._start_indexing(paths)

    def _start_indexing(self, file_paths: list):
        """Lance l'indexation d'une liste de fichiers dans un thread séparé."""
        if not self.ingestion:
            QMessageBox.warning(self, "Erreur", "Moteur d'ingestion non disponible.")
            return

        # Filtrer les extensions supportées
        valid = [p for p in file_paths if Path(p).suffix.lower() in self.SUPPORTED_EXTS]
        if not valid:
            QMessageBox.information(self, "Aucun fichier", "Aucun fichier au format supporté sélectionné.")
            return

        self.index_progress.setVisible(True)
        self.index_status.setVisible(True)
        self.index_progress.setMaximum(len(valid))
        self.index_progress.setValue(0)
        plural = "s" if len(valid) > 1 else ""
        self.index_status.setText(f"⏳ Indexation de {len(valid)} fichier{plural}…")

        self.index_worker = IndexWorker(self.ingestion, valid)
        self.index_worker.progress.connect(self._on_index_progress)
        self.index_worker.finished.connect(self._on_index_finished)
        self.index_worker.error.connect(self._on_index_error)
        self.index_worker.start()

    def _on_index_progress(self, current, total, filename):
        self.index_progress.setMaximum(total)
        self.index_progress.setValue(current)
        if total > 1:
            self.index_status.setText(f"⏳ Indexation : {current}/{total} — {filename}")
        else:
            self.index_status.setText(f"⏳ Indexation de {filename}…")

    def _on_index_finished(self, result):
        self.index_progress.setVisible(False)
        self.index_status.setVisible(True)
        if result["errors"]:
            err_summary = "\n".join(
                f"• {name}: {err}" for name, err in result["errors"][:5]
            )
            self.index_status.setText(
                f"✅ {result['indexed']}/{result['total']} indexés "
                f"({result['duration_s']}s) — ⚠ {len(result['errors'])} erreurs:\n{err_summary}"
            )
        else:
            self.index_status.setText(
                f"✅ {result['indexed']}/{result['total']} fichier"
                f"{'s' if result['total'] != 1 else ''} indexé"
                f"{'s' if result['total'] != 1 else ''} "
                f"en {result['duration_s']}s"
            )
        self.load_documents()

    def _on_index_error(self, filename, error):
        self.index_status.setText(f"⚠ Erreur {filename}: {error}")

    # ─────────── DELETE ───────────

    def _delete_selected(self):
        """Supprime de l'index les documents sélectionnés dans le tableau."""
        rows = set(i.row() for i in self.table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "Suppression", "Sélectionnez d'abord des documents dans le tableau.")
            return
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer {len(rows)} document{'s' if len(rows) > 1 else ''} "
            f"de l'index RAG ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            conn = self.rag_engine._get_conn()
            for row in rows:
                filepath = self.table.item(row, 0).data(Qt.UserRole)
                if not filepath:
                    continue
                source_name = os.path.basename(filepath)
                conn.execute("DELETE FROM indexed_files WHERE filepath = ?", (filepath,))
                self.rag_engine.remove_file_index(source_name)
            conn.commit()
            conn.close()
            self.load_documents()
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Suppression échouée : {e}")

    # ─────────── REINDEX ───────────

    def _reindex_selected(self):
        """Réindexe les documents sélectionnés."""
        rows = set(i.row() for i in self.table.selectedIndexes())
        if not rows:
            return
        paths = []
        for row in rows:
            fp = self.table.item(row, 0).data(Qt.UserRole)
            if fp:
                paths.append(fp)
        if paths:
            self._start_indexing(paths)

    # ─────────── SEARCH & FILTER ───────────

    def _on_search(self, text):
        self._apply_filters_and_sort()

    def _on_type_filter(self, text):
        self._apply_filters_and_sort()

    def _on_date_filter(self, text):
        self._apply_filters_and_sort()

    def _on_sort_changed(self, text):
        self._apply_filters_and_sort()

    # ─────────── CONTEXT MENU ───────────

    def _on_context_menu(self, pos):
        """Menu contextuel du clic droit sur le tableau."""
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        filepath = self.table.item(row, 0).data(Qt.UserRole) or ""
        name = self.table.item(row, 0).text()

        menu = QMenu(self)

        action_delete = QAction("🗑 Supprimer", self)
        action_delete.triggered.connect(self._delete_selected)
        menu.addAction(action_delete)

        action_reindex = QAction("🔄 Réindexer", self)
        action_reindex.triggered.connect(self._reindex_selected)
        menu.addAction(action_reindex)

        action_preview = QAction("👁 Prévisualiser", self)
        action_preview.triggered.connect(lambda: self._preview_file(filepath))
        menu.addAction(action_preview)

        action_open = QAction("📂 Ouvrir emplacement", self)
        action_open.triggered.connect(lambda: self._open_file_location(filepath))
        menu.addAction(action_open)

        action_meta = QAction("ℹ Métadonnées", self)
        action_meta.triggered.connect(lambda: self._show_metadata(row, filepath))
        menu.addAction(action_meta)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _preview_file(self, filepath: str):
        """Tente d'ouvrir le fichier avec l'application par défaut du système."""
        if not filepath or not os.path.exists(filepath):
            QMessageBox.warning(self, "Prévisualisation", "Fichier introuvable.")
            return
        import subprocess
        subprocess.Popen(["open", filepath])

    def _open_file_location(self, filepath: str):
        """Ouvre le dossier contenant le fichier dans le Finder."""
        if not filepath:
            return
        folder = os.path.dirname(filepath)
        if os.path.isdir(folder):
            import subprocess
            subprocess.Popen(["open", folder])

    def _show_metadata(self, row: int, filepath: str):
        """Affiche les métadonnées du document."""
        if not filepath:
            return
        doc = self._documents_data[row] if row < len(self._documents_data) else None
        if not doc:
            return
        lines = [
            f"📄 {doc['name']}",
            f"📁 {filepath}",
            f"📐 Type: {doc['ext_upper']}",
            f"📦 Taille: {doc['size_str']}",
            f"📑 Pages: {doc['pages']}",
            f"🧩 Chunks: {doc['chunks']}",
            f"📅 Indexé le: {doc['date_str']}",
            f"✅ Statut: {doc['status']}",
        ]
        if doc.get("hash"):
            lines.append(f"🔑 Hash: {doc['hash'][:16]}…")
        QMessageBox.information(self, "Métadonnées", "\n".join(lines))

    # ─────────── RAG DEBUG ───────────

    def _toggle_debug_panel(self, visible: bool):
        self.debug_panel.setVisible(visible)
        if visible:
            self.debug_query_input.setFocus()

    def _on_debug_search(self):
        """Interroge le moteur RAG et affiche les résultats de débogage."""
        query = self.debug_query_input.text().strip()
        if not query:
            return
        if not self.rag_engine:
            self.debug_context.setPlainText("⚠ Moteur RAG non connecté.")
            return

        import asyncio

        async def _do_debug():
            try:
                context, result = await self.rag_engine.retrieve(query, k=5)
                # Métriques
                self.lbl_debug_docs.setText(f"Documents retrouvés: {result.documents_found}")
                self.lbl_debug_chunks.setText(f"Chunks sélectionnés: {result.chunks_injected}")
                self.lbl_debug_score.setText(f"Score similarité: {result.top_score:.4f}")
                self.lbl_debug_time.setText(f"Temps: {result.retrieval_time_ms:.1f} ms")

                # Contexte formaté
                if context:
                    self.debug_context.setPlainText(context)
                else:
                    if result.rejected_chunks > 0:
                        self.debug_context.setPlainText(
                            f"⛔ Requête rejetée par la Confidence Gate.\n"
                            f"Raison: {result.rejection_reason}\n\n"
                            f"Chunks récupérés mais rejetés: {result.rejected_chunks}\n"
                            f"Score max: {result.top_score:.4f}\n"
                            f"Seuil minimum requis: 0.60\n"
                            f"Seuil fallback (FTS): 0.40"
                        )
                    else:
                        self.debug_context.setPlainText("Aucun chunk trouvé pour cette requête.")
            except Exception as e:
                self.debug_context.setPlainText(f"❌ Erreur lors de la recherche RAG:\n{e}")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # On est déjà dans un event loop (ex: qasync)
                import threading
                t = threading.Thread(target=lambda: asyncio.run(_do_debug()), daemon=True)
                t.start()
            else:
                loop.run_until_complete(_do_debug())
        except RuntimeError:
            asyncio.run(_do_debug())

    # ─────────── UTILITIES ───────────

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} o"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} Ko"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} Mo"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} Go"

    # ─────────── DRAG & DROP ───────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                ext = Path(path).suffix.lower()
                if ext in self.SUPPORTED_EXTS:
                    paths.append(path)
        if paths:
            self._start_indexing(paths)
        else:
            event.ignore()

    # ─────────── SHOW EVENT ───────────

    def showEvent(self, event):
        super().showEvent(event)
        self.load_documents()
