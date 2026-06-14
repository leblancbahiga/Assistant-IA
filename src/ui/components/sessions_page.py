"""
Sessions Page — Gestion complète de l'historique des sessions de chat.
Liste, recherche, renommer, dupliquer, exporter et supprimer.
"""
import json
import datetime
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QMessageBox, QInputDialog,
    QFileDialog, QDialog, QListWidget, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal

logger = logging.getLogger(__name__)


class FormatDialog(QDialog):
    """Dialogue pour choisir le format d'export."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choisir le format d'export")
        self.setFixedSize(280, 180)
        self.setObjectName("FormatDialog")
        self.setStyleSheet("""
            QDialog#FormatDialog {
                background-color: #121826;
                border: 1px solid rgba(0, 242, 255, 0.2);
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📤 Exporter la session")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.format_list = QListWidget()
        self.format_list.setObjectName("StyledCombo")
        self.format_list.addItems(["Markdown (.md)", "JSON (.json)", "PDF (.pdf)"])
        self.format_list.setCurrentRow(0)
        self.format_list.setFixedHeight(80)
        layout.addWidget(self.format_list)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def selected_format(self) -> str:
        text = self.format_list.currentItem().text()
        if "Markdown" in text:
            return "md"
        elif "JSON" in text:
            return "json"
        elif "PDF" in text:
            return "pdf"
        return "md"


class SessionsPage(QWidget):
    session_selected = Signal(str)  # émis quand une session est chargée (session_id)

    def __init__(self, memory_store=None, parent=None):
        super().__init__(parent)
        self.memory_store = memory_store
        self._sessions = []  # liste de dicts représentant les sessions
        self._filtered_sessions = []
        self._session_store = None
        try:
            from src.session.store import SessionStore
            self._session_store = SessionStore()
        except Exception:
            pass
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ─── HEADER ────────────────────────────────────────
        header = QHBoxLayout()

        title = QLabel("🕒 HISTORIQUE DES SESSIONS")
        title.setObjectName("PageTitle")

        btn_refresh = QPushButton("↻")
        btn_refresh.setObjectName("GhostBtn")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.load_sessions)

        btn_export_all = QPushButton("📤 Exporter")
        btn_export_all.setObjectName("GhostBtn")
        btn_export_all.setCursor(Qt.PointingHandCursor)
        btn_export_all.clicked.connect(self._export_all)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_refresh)
        header.addWidget(btn_export_all)
        layout.addLayout(header)

        # ─── STATS BAR ─────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setObjectName("Panel")
        stats_frame.setFixedHeight(45)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 5, 15, 5)

        self.stat_sessions = QLabel("0 sessions")
        self.stat_sessions.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.stat_messages = QLabel("0 messages")
        self.stat_messages.setStyleSheet("color: #6B7280; font-size: 11px;")
        stats_layout.addWidget(self.stat_sessions)
        stats_layout.addStretch()
        stats_layout.addWidget(self.stat_messages)
        layout.addWidget(stats_frame)

        # ─── FILTER BAR ────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")
        filter_frame.setFixedHeight(48)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 4, 12, 4)
        filter_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SessionSearchInput")
        self.search_input.setPlaceholderText("Rechercher dans les sessions…")
        self.search_input.textChanged.connect(self._on_search_changed)

        self.model_filter = QComboBox()
        self.model_filter.setObjectName("SessionModelFilter")
        self.model_filter.addItems(["Tous modèles", "Qwen 3B", "Deepseek", "Gemini", "Groq"])
        self.model_filter.currentTextChanged.connect(self._on_filter_changed)

        self.date_filter = QComboBox()
        self.date_filter.setObjectName("SessionDateFilter")
        self.date_filter.addItems(["Toutes dates", "Aujourd'hui", "7 jours", "30 jours"])
        self.date_filter.currentTextChanged.connect(self._on_filter_changed)

        filter_layout.addWidget(self.search_input, stretch=1)
        filter_layout.addWidget(QLabel("Modèle :"))
        filter_layout.addWidget(self.model_filter)
        filter_layout.addWidget(QLabel("Période :"))
        filter_layout.addWidget(self.date_filter)
        layout.addWidget(filter_frame)

        # ─── TABLE ─────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setObjectName("SessionTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Session", "Date création", "Messages", "Modèle", "Temps réponse", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        # ─── EMPTY STATE ───────────────────────────────────
        self.empty_label = QLabel(
            "Aucune session pour le moment.\n"
            "Commencez à discuter dans la Console pour voir l'historique ici."
        )
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            "color: #4B5563; font-size: 14px; padding: 40px;"
        )
        layout.addWidget(self.empty_label)

    # ──────────────── CHARGEMENT DES SESSIONS ────────────────

    def showEvent(self, event):
        """Charge les sessions quand la page devient visible."""
        super().showEvent(event)
        if self.memory_store is not None and hasattr(self, '_loaded'):
            self.load_sessions()
        self._loaded = True

    def load_sessions(self):
        """Charge les sessions depuis SessionStore (puis memory_store en fallback)."""
        self._sessions.clear()

        # Essayer SessionStore d'abord
        if self._session_store is not None:
            try:
                raw = self._session_store.list_sessions(limit=100)
                for entry in raw:
                    session = self._session_store.get_or_create(entry["id"])
                    normalized = self._session_to_dict(session, entry)
                    self._sessions.append(normalized)
                self._apply_filters()
                if not self._sessions:
                    self._show_empty_state()
                return
            except Exception as e:
                logger.error("SessionStore: %s", e)

        # Fallback : memory_store
        if not self.memory_store:
            self._show_empty_state("⚠️ Aucune source de données")
            return

        try:
            history = self.memory_store.get_recent_history(limit=200)
            if not history:
                self._show_empty_state()
                return
            sessions = self._group_into_sessions(history)
            self._sessions = sessions
            self._apply_filters()
        except Exception as e:
            logger.error(f"Erreur chargement sessions: {e}")
            self._show_empty_state(f"Erreur : {str(e)}")

    @staticmethod
    def _session_to_dict(session, entry: dict) -> dict:
        """Convertit un objet Session en dict pour le tableau."""
        from datetime import datetime
        created = datetime.fromtimestamp(session.created_at)
        date_str = created.strftime("%d/%m/%Y %H:%M")

        content_lines = []
        for m in session.messages:
            role = "Utilisateur" if m.role == "user" else "NURU"
            content_lines.append(f"{role}: {m.content}")
        full_text = "\n\n".join(content_lines)

        model = "—"
        msgs = session.messages
        if msgs and msgs[-1].metadata and "intent" in msgs[-1].metadata:
            model = msgs[-1].metadata.get("intent", "—")

        return {
            "title": session.title or (msgs[0].content[:80] + "…" if msgs and msgs[0].content else "Sans titre"),
            "date": date_str,
            "datetime": created,
            "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in msgs],
            "msg_count": entry.get("message_count", len(msgs)),
            "model": model,
            "avg_time": 0.0,
            "time_str": "—",
            "full_text": full_text,
            "session_id": session.id,
        }

    def _group_into_sessions(self, history: list) -> list:
        """Groupe les messages en sessions basées sur l'ordre et le temps."""
        if not history:
            return []

        sessions = []
        current_msgs = [history[0]]
        current_date = self._parse_timestamp(history[0])

        for msg in history[1:]:
            msg_date = self._parse_timestamp(msg)
            # Nouvelle session si écart > 30 min ou si le rôle repasse à 'user' après une réponse
            gap = self._gap_minutes(current_date, msg_date) if current_date and msg_date else 0
            if gap > 30:
                sessions.append(self._make_session(current_msgs))
                current_msgs = [msg]
            else:
                current_msgs.append(msg)
            current_date = msg_date

        if current_msgs:
            sessions.append(self._make_session(current_msgs))

        # Numéroter les sessions en ordre inverse (plus récente en premier)
        sessions.reverse()
        for i, s in enumerate(sessions):
            s["id"] = i
            if not s["title"]:
                s["title"] = f"Session #{i + 1}"
        return sessions

    def _parse_timestamp(self, msg: dict):
        """Extrait un datetime depuis un message."""
        ts = msg.get("timestamp", "")
        if isinstance(ts, datetime.datetime):
            return ts
        if isinstance(ts, str) and ts:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S"):
                try:
                    return datetime.datetime.strptime(ts, fmt)
                except ValueError:
                    continue
        return None

    def _gap_minutes(self, d1: datetime.datetime, d2: datetime.datetime) -> float:
        """Écart en minutes entre deux dates."""
        if not d1 or not d2:
            return 0
        return abs((d2 - d1).total_seconds()) / 60

    def _make_session(self, messages: list) -> dict:
        """Construit un dict session à partir d'une liste de messages."""
        if not messages:
            return {}

        # Titre : premier message utilisateur ou premier message
        first_user = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"),
            messages[0].get("content", "Sans titre")
        )
        title = first_user[:80] + ("…" if len(first_user) > 80 else "")

        # Date
        first_ts = self._parse_timestamp(messages[0])
        date_str = first_ts.strftime("%d/%m/%Y %H:%M") if first_ts else "—"

        # Modèle et temps de réponse (si disponibles dans les données réelles)
        model = messages[0].get("model", "—") if messages else "—"
        
        # Temps de réponse réel si disponible
        processing_times = [m.get("processing_time", 0) for m in messages if m.get("processing_time")]
        avg_time = 0.0
        if processing_times:
            avg_time = round(sum(processing_times) / len(processing_times), 1)
            time_str = f"{avg_time}s"
        else:
            time_str = "—"

        msg_count = len(messages)

        # Contenu complet pour export
        content_lines = []
        for m in messages:
            role = "Utilisateur" if m.get("role") == "user" else "NURU"
            content_lines.append(f"{role}: {m.get('content', '')}")
        full_text = "\n\n".join(content_lines)

        return {
            "title": title,
            "date": date_str,
            "datetime": first_ts or datetime.datetime.now(),
            "messages": messages,
            "msg_count": msg_count,
            "model": model,
            "avg_time": avg_time,
            "time_str": time_str,
            "full_text": full_text,
        }

    # ──────────────── FILTRAGE ET RECHERCHE ────────────────

    def _on_search_changed(self, text: str):
        self._apply_filters()

    def _on_filter_changed(self, _):
        self._apply_filters()

    def search_sessions(self, text: str):
        """Filtre le tableau par texte de recherche."""
        self.search_input.setText(text)

    def _apply_filters(self):
        """Applique les filtres et met à jour le tableau."""
        search_text = self.search_input.text().strip().lower()
        model_filter = self.model_filter.currentText()
        date_filter = self.date_filter.currentText()

        self._filtered_sessions = []
        for s in self._sessions:
            # Filtre texte
            if search_text and search_text not in s["title"].lower():
                continue

            # Filtre modèle
            if model_filter != "Tous modèles" and s["model"] != model_filter:
                continue

            # Filtre date
            if date_filter != "Toutes dates" and s["datetime"]:
                now = datetime.datetime.now()
                if date_filter == "Aujourd'hui":
                    if s["datetime"].date() != now.date():
                        continue
                elif date_filter == "7 jours":
                    delta = (now - s["datetime"]).days
                    if delta > 7:
                        continue
                elif date_filter == "30 jours":
                    delta = (now - s["datetime"]).days
                    if delta > 30:
                        continue

            self._filtered_sessions.append(s)

        self._populate_table(self._filtered_sessions)

    def _populate_table(self, sessions: list):
        """Remplit le QTableWidget avec les sessions."""
        self.table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            # Session (titre)
            self.table.setItem(row, 0, QTableWidgetItem(s["title"]))
            # Date création
            self.table.setItem(row, 1, QTableWidgetItem(s["date"]))
            # Messages
            self.table.setItem(row, 2, QTableWidgetItem(str(s["msg_count"])))
            # Modèle
            self.table.setItem(row, 3, QTableWidgetItem(s["model"]))
            # Temps réponse
            self.table.setItem(row, 4, QTableWidgetItem(s["time_str"]))

            # ─── Actions ───
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            btn_rename = QPushButton("✏️")
            btn_rename.setFixedSize(28, 28)
            btn_rename.setToolTip("Renommer la session")
            btn_rename.setCursor(Qt.PointingHandCursor)
            btn_rename.clicked.connect(lambda checked, r=row: self._on_row_rename(r))

            btn_duplicate = QPushButton("📋")
            btn_duplicate.setFixedSize(28, 28)
            btn_duplicate.setToolTip("Dupliquer la session")
            btn_duplicate.setCursor(Qt.PointingHandCursor)
            btn_duplicate.clicked.connect(lambda checked, r=row: self._on_row_duplicate(r))

            btn_export = QPushButton("📤")
            btn_export.setFixedSize(28, 28)
            btn_export.setToolTip("Exporter la session")
            btn_export.setCursor(Qt.PointingHandCursor)
            btn_export.clicked.connect(lambda checked, r=row: self._on_row_export(r))

            btn_delete = QPushButton("🗑️")
            btn_delete.setFixedSize(28, 28)
            btn_delete.setToolTip("Supprimer la session")
            btn_delete.setCursor(Qt.PointingHandCursor)
            btn_delete.clicked.connect(lambda checked, r=row: self._on_row_delete(r))

            # Style des mini boutons
            btn_style = (
                "QPushButton { background: transparent; border: 1px solid rgba(255,255,255,0.1);"
                " border-radius: 14px; font-size: 12px; }"
                "QPushButton:hover { background: rgba(0,242,255,0.15);"
                " border: 1px solid rgba(0,242,255,0.3); }"
            )
            for btn in (btn_rename, btn_duplicate, btn_export, btn_delete):
                btn.setStyleSheet(btn_style)

            actions_layout.addWidget(btn_rename)
            actions_layout.addWidget(btn_duplicate)
            actions_layout.addWidget(btn_export)
            actions_layout.addWidget(btn_delete)

            self.table.setCellWidget(row, 5, actions_widget)

        # Mise à jour stats
        total_sessions = len(self._sessions)
        shown = len(sessions)
        total_msgs = sum(s["msg_count"] for s in sessions)

        if shown == total_sessions:
            self.stat_sessions.setText(f"{total_sessions} session{'s' if total_sessions != 1 else ''}")
        else:
            self.stat_sessions.setText(f"{shown} / {total_sessions} session{'s' if total_sessions != 1 else ''}")

        self.stat_messages.setText(f"{total_msgs} message{'s' if total_msgs != 1 else ''}")

        # Visibilité empty state
        has_data = len(sessions) > 0
        self.table.setVisible(has_data)
        self.empty_label.setVisible(not has_data)

    # ──────────────── ÉTAT VIDE ────────────────────────────

    def _show_empty_state(self, message: str = None):
        """Affiche l'état vide avec un message optionnel."""
        self.table.setRowCount(0)
        self.table.setVisible(False)
        if message:
            self.empty_label.setText(message)
        else:
            self.empty_label.setText(
                "Aucune session pour le moment.\n"
                "Commencez à discuter dans la Console pour voir l'historique ici."
            )
        self.empty_label.setVisible(True)
        self.stat_sessions.setText("0 sessions")
        self.stat_messages.setText("0 messages")

    # ──────────────── ACTIONS SUR LES LIGNES ────────────────

    def _get_session_by_row(self, row: int) -> dict:
        """Récupère la session correspondant à une ligne du tableau."""
        if 0 <= row < len(self._filtered_sessions):
            return self._filtered_sessions[row]
        return None

    def rename_session(self, session_id) -> bool:
        """Renomme une session via son id. Retourne True si réussi."""
        for s in self._sessions:
            if s.get("id") == session_id:
                new_title, ok = QInputDialog.getText(
                    self, "Renommer la session",
                    "Nouveau nom :",
                    text=s["title"]
                )
                if ok and new_title.strip():
                    s["title"] = new_title.strip()
                    self._apply_filters()
                    return True
                return False
        return False

    def _on_row_rename(self, row: int):
        """Boîte de dialogue pour renommer une session."""
        s = self._get_session_by_row(row)
        if not s:
            return
        new_title, ok = QInputDialog.getText(
            self, "Renommer la session",
            "Nouveau nom :",
            text=s["title"]
        )
        if ok and new_title.strip():
            s["title"] = new_title.strip()
            # Persister dans SessionStore
            if self._session_store:
                session_id = s.get("id", "")
                self._session_store.update_title(str(session_id), s["title"])
            self._apply_filters()

    def duplicate_session(self, session_id) -> bool:
        """Duplique une session. Retourne True si réussi."""
        for s in self._sessions:
            if s.get("id") == session_id:
                dup = dict(s)
                dup["title"] = f"Copie de {s['title']}"
                dup["id"] = max((x.get("id", 0) for x in self._sessions), default=0) + 1
                self._sessions.insert(0, dup)
                self._apply_filters()
                return True
        return False

    def _on_row_duplicate(self, row: int):
        """Duplique une session."""
        s = self._get_session_by_row(row)
        if not s:
            return
        dup = dict(s)
        dup["title"] = f"Copie de {s['title']}"
        dup["id"] = max((x.get("id", 0) for x in self._sessions), default=0) + 1
        self._sessions.insert(0, dup)
        self._apply_filters()

    def export_session(self, session_id, format: str = "md") -> bool:
        """Exporte une session dans le format spécifié. Retourne True si réussi."""
        s = None
        for session in self._sessions:
            if session.get("id") == session_id:
                s = session
                break
        if not s:
            return False
        return self._do_export(s, format)

    def _on_row_export(self, row: int):
        """Choisir le format et exporter une session."""
        s = self._get_session_by_row(row)
        if not s:
            return

        dialog = FormatDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        fmt = dialog.selected_format()
        self._do_export(s, fmt)

    def _do_export(self, session: dict, fmt: str) -> bool:
        """Sauvegarde une session dans un fichier."""
        ext_map = {"md": "Markdown (*.md)", "json": "JSON (*.json)", "pdf": "PDF (*.pdf)"}
        filter_str = ext_map.get(fmt, "Markdown (*.md)")

        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in session["title"])
        default_name = f"session_{safe_title[:40]}.{fmt}"

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Exporter la session", default_name, filter_str
        )
        if not filepath:
            return False

        try:
            content = self._format_export(session, fmt)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(
                self, "Export réussi",
                f"✅ Session exportée avec succès :\n{filepath}"
            )
            logger.info(f"Session exportée : {filepath}")
            return True
        except Exception as e:
            QMessageBox.warning(
                self, "Erreur d'export",
                f"❌ Impossible d'exporter la session :\n{e}"
            )
            logger.error(f"Erreur export session: {e}")
            return False

    def _format_export(self, session: dict, fmt: str) -> str:
        """Formate le contenu d'une session pour l'export."""
        if fmt == "json":
            data = {
                "title": session["title"],
                "date": session["date"],
                "model": session["model"],
                "message_count": session["msg_count"],
                "messages": [
                    {"role": m.get("role", "?"), "content": m.get("content", "")}
                    for m in session.get("messages", [])
                ]
            }
            return json.dumps(data, ensure_ascii=False, indent=2)

        # Markdown (et PDF via Markdown simplifié)
        lines = [
            f"# Session : {session['title']}",
            "",
            f"**Date :** {session['date']}",
            f"**Modèle :** {session['model']}",
            f"**Messages :** {session['msg_count']}",
            f"**Temps moyen :** {session['time_str']}",
            "",
            "---",
            "",
        ]
        for m in session.get("messages", []):
            role = "👤 **Utilisateur**" if m.get("role") == "user" else "🤖 **NURU**"
            lines.append(f"### {role}")
            lines.append("")
            lines.append(m.get("content", ""))
            lines.append("")

        return "\n".join(lines)

    def delete_session(self, session_id) -> bool:
        """Supprime une session après confirmation. Retourne True si supprimé."""
        for i, s in enumerate(self._sessions):
            if s.get("id") == session_id:
                reply = QMessageBox.question(
                    self, "Supprimer la session",
                    f"Voulez-vous vraiment supprimer la session\n« {s['title']} » ?\n\nCette action est irréversible.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._sessions.pop(i)
                    self._apply_filters()
                    return True
                return False
        return False

    def _on_row_delete(self, row: int):
        """Confirme puis supprime une session."""
        s = self._get_session_by_row(row)
        if not s:
            return
        reply = QMessageBox.question(
            self, "Supprimer la session",
            f"Voulez-vous vraiment supprimer la session\n« {s['title']} » ?\n\nCette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # Supprimer du SessionStore si disponible
                if self._session_store:
                    session_id = s.get("id", "")
                    self._session_store.delete_session(str(session_id))
                self._sessions.remove(s)
                self._apply_filters()
            except ValueError:
                pass

    # ──────────────── EXPORT TOUTES LES SESSIONS ────────────

    def _export_all(self):
        """Exporter toutes les sessions en un seul fichier."""
        if not self._sessions:
            QMessageBox.information(self, "Export", "Aucune session à exporter.")
            return

        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Exporter toutes les sessions",
            "toutes_les_sessions.json",
            "JSON (*.json);;Markdown (*.md)"
        )
        if not filepath:
            return

        fmt = "json" if "JSON" in selected_filter else "md"

        try:
            if fmt == "json":
                data = []
                for s in self._sessions:
                    data.append({
                        "title": s["title"],
                        "date": s["date"],
                        "model": s["model"],
                        "message_count": s["msg_count"],
                        "messages": [
                            {"role": m.get("role", "?"), "content": m.get("content", "")}
                            for m in s.get("messages", [])
                        ]
                    })
                content = json.dumps(data, ensure_ascii=False, indent=2)
            else:
                lines = ["# Toutes les sessions\n"]
                for s in self._sessions:
                    lines.append(f"## {s['title']}")
                    lines.append("")
                    lines.append(f"- **Date :** {s['date']}")
                    lines.append(f"- **Modèle :** {s['model']}")
                    lines.append(f"- **Messages :** {s['msg_count']}")
                    lines.append("")
                    for m in s.get("messages", []):
                        role = "👤 **Utilisateur**" if m.get("role") == "user" else "🤖 **NURU**"
                        lines.append(f"### {role}")
                        lines.append("")
                        lines.append(m.get("content", ""))
                        lines.append("")
                    lines.append("---\n")
                content = "\n".join(lines)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(
                self, "Export réussi",
                f"✅ {len(self._sessions)} sessions exportées :\n{filepath}"
            )
            logger.info(f"Toutes les sessions exportées : {filepath}")
        except Exception as e:
            QMessageBox.warning(
                self, "Erreur d'export",
                f"❌ Impossible d'exporter :\n{e}"
            )
            logger.error(f"Erreur export toutes sessions: {e}")

    # ──────────────── AFFICHAGE ────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._sessions:
            self.load_sessions()
