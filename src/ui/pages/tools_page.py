"""NURU V16 — Tools Page.
Gestionnaire d'outils MCP interactif : liste, détails, exécution.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QLineEdit, QTextEdit, QSplitter, QDialog, QDialogButtonBox,
    QFormLayout, QInputDialog, QMessageBox,
)

from src.ui.tokens import Color, Spacing, Typography, Radius

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class ToolCard(QFrame):
    """Carte outil cliquable."""

    clicked = None  # pas de Signal, on utilise mousePressEvent

    def __init__(self, name: str, description: str, server: str = "", parent=None):
        super().__init__(parent)
        self.tool_name = name
        self.tool_server = server
        self.setObjectName("ToolCard")
        self.setFixedSize(260, 100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(4)

        top = QHBoxLayout()
        icon = QLabel("🔧")
        icon.setStyleSheet("font-size: 18pt;")
        top.addWidget(icon)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {_PAL['text']}; font-size: 11pt; "
            f"font-weight: {Typography.WEIGHT_BOLD};"
        )
        top.addWidget(name_lbl)
        top.addStretch()

        if server:
            svr = QLabel(f"⚡ {server}")
            svr.setStyleSheet(f"color: {Color.CYAN}; font-size: 8pt;")
            top.addWidget(svr)

        layout.addLayout(top)

        desc = QLabel(description[:80])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 9pt;")
        layout.addWidget(desc)

    def mousePressEvent(self, event):
        parent = self.parent()
        while parent and not hasattr(parent, '_on_tool_clicked'):
            parent = parent.parent()
        if parent:
            parent._on_tool_clicked(self.tool_name, self.tool_server)
        super().mousePressEvent(event)


class ToolDetailPanel(QFrame):
    """Panneau de détail et d'exécution d'un outil."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolDetailPanel")
        self._tool_name = ""
        self._tool_handler = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.SM)

        # Header
        self._title = QLabel("Sélectionne un outil")
        self._title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: 13pt; "
            f"font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(self._title)

        self._desc = QLabel("Clique sur une carte outil pour voir les détails")
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 10pt;")
        layout.addWidget(self._desc)

        # Paramètres
        params_label = QLabel("Paramètres")
        params_label.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: 10pt; "
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(params_label)

        self._params_widget = QWidget()
        self._params_layout = QFormLayout(self._params_widget)
        self._params_layout.setSpacing(4)
        layout.addWidget(self._params_widget)

        # Execute
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("🚀 Exécuter")
        self._run_btn.setStyleSheet(
            f"background: {Color.CYAN}; color: #05080F; font-weight: bold; "
            f"padding: 8px 24px; border-radius: {Radius.SMALL};"
        )
        self._run_btn.clicked.connect(self._execute)
        self._run_btn.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self._run_btn)

        # Reset button
        self._reset_btn = QPushButton("Réinitialiser")
        self._reset_btn.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; padding: 8px 16px;"
        )
        self._reset_btn.clicked.connect(self._reset_params)
        self._reset_btn.setVisible(False)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        # Résultat
        result_label = QLabel("Résultat")
        result_label.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: 10pt; "
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(result_label)

        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(200)
        self._result.setStyleSheet(
            f"background: rgba(0,0,0,0.3); border: 1px solid {Color.BORDER}; "
            f"border-radius: {Radius.SMALL}; color: {Color.TEXT_PRIMARY}; "
            f"padding: 8px; font-family: 'SF Mono', monospace; font-size: 9pt;"
        )
        layout.addWidget(self._result, stretch=1)

    def show_tool(self, name: str, handler: Any, params: dict) -> None:
        """Affiche un outil et ses paramètres."""
        self._tool_name = name
        self._tool_handler = handler
        self._title.setText(f"🔧  {name}")
        self._desc.setText(getattr(handler, 'description', '') if handler else '')

        # Vider les anciens paramètres
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._param_fields = {}
        self._reset_btn.setVisible(True)

        param_defs = params if isinstance(params, dict) else {}

        if param_defs:
            self._run_btn.setEnabled(True)
            for pname, pinfo in param_defs.items():
                required = pinfo.get("required", False)
                label = f"{pname}{' *' if required else ''}"
                ptype = pinfo.get("type", "string")

                if ptype == "string":
                    field = QLineEdit()
                    field.setPlaceholderText(pinfo.get("description", ""))
                    field.setStyleSheet(
                        f"background: rgba(0,0,0,0.3); border: 1px solid {Color.BORDER}; "
                        f"border-radius: {Radius.SMALL}; color: {Color.TEXT_PRIMARY}; "
                        f"padding: 6px;"
                    )
                elif ptype == "integer":
                    field = QLineEdit()
                    field.setPlaceholderText("0")
                    field.setStyleSheet(
                        f"background: rgba(0,0,0,0.3); border: 1px solid {Color.BORDER}; "
                        f"border-radius: {Radius.SMALL}; color: {Color.TEXT_PRIMARY}; "
                        f"padding: 6px;"
                    )
                else:
                    field = QLabel(f"(type: {ptype})")
                    field.setStyleSheet(f"color: {Color.TEXT_MUTED};")

                self._params_layout.addRow(label, field)
                self._param_fields[pname] = (field, ptype, required)
        else:
            self._run_btn.setEnabled(True)
            no_params = QLabel("Aucun paramètre requis")
            no_params.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-style: italic;")
            self._params_layout.addRow(no_params)

    def _reset_params(self) -> None:
        """Réinitialise les champs de paramètres."""
        for name, (field, ptype, _) in getattr(self, '_param_fields', {}).items():
            if isinstance(field, QLineEdit):
                field.clear()
        self._result.clear()

    def _execute(self) -> None:
        """Exécute l'outil avec les paramètres saisis."""
        if not self._tool_handler:
            return

        params = {}
        for name, (field, ptype, required) in getattr(self, '_param_fields', {}).items():
            if isinstance(field, QLineEdit):
                val = field.text().strip()
                if not val and required:
                    QMessageBox.warning(self, "Champ requis", f"'{name}' est requis")
                    return
                if val:
                    if ptype == "integer":
                        try:
                            params[name] = int(val)
                        except ValueError:
                            QMessageBox.warning(self, "Erreur", f"'{name}' doit être un entier")
                            return
                    else:
                        params[name] = val

        self._result.setPlainText("⏳ Exécution en cours...")
        self._run_btn.setEnabled(False)

        try:
            handler = self._tool_handler
            if hasattr(handler, 'handler') and callable(handler.handler):
                result = handler.handler(**params)
            elif callable(handler):
                result = handler(**params)
            else:
                result = {"error": "Handler non callable"}

            if isinstance(result, dict):
                text = json.dumps(result, indent=2, ensure_ascii=False)
            else:
                text = str(result)
            self._result.setPlainText(text)
        except Exception as e:
            self._result.setPlainText(f"❌ Erreur : {e}")
            logger.exception(f"Tool execution failed: {e}")
        finally:
            self._run_btn.setEnabled(True)


class ToolsPage(QWidget):
    """Page Outils V16 — exploration et exécution des outils MCP."""

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolsPageV16")
        self._engine = engine
        self._tools_list: list[tuple[str, Any, dict]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        # Header
        header = QHBoxLayout()
        title = QLabel("🔧  Outils")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        header.addWidget(title)

        self._count = QLabel()
        self._count.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 10pt;")
        header.addWidget(self._count)
        header.addStretch()
        layout.addLayout(header)

        # Splitter grille / détail
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Grille d'outils (gauche)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setSpacing(Spacing.SM)
        scroll.setWidget(grid_widget)
        splitter.addWidget(scroll)

        # Panneau détail (droite)
        self._detail = ToolDetailPanel()
        splitter.addWidget(self._detail)
        splitter.setSizes([400, 350])

        layout.addWidget(splitter, stretch=1)

        # Pied : connexions MCP
        self._conn_info = QLabel()
        self._conn_info.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 9pt;")
        layout.addWidget(self._conn_info)

        # Charger les outils
        self._build_tools()

    def _on_tool_clicked(self, name: str, server: str) -> None:
        """Ouvre le détail d'un outil."""
        for n, handler, params in self._tools_list:
            if n == name:
                self._detail.show_tool(name, handler, params)
                return

    def _build_tools(self) -> None:
        """Charge les outils depuis le backend MCP."""
        mcp_servers = 0
        mcp_tools = 0

        if self._engine:
            server = self._engine.mcp_server
            if server and hasattr(server, 'tools'):
                for name, tool in server.tools.items():
                    params = getattr(tool, 'parameters', {})
                    self._tools_list.append((
                        name,
                        tool,
                        params,
                    ))
                mcp_tools = len(server.tools)
                mcp_servers = 1

            client = self._engine.mcp_client
            if client and hasattr(client, 'connections'):
                mcp_servers += len([
                    c for c in client.connections
                    if getattr(c, 'enabled', True)
                ])
                if hasattr(client, 'tools'):
                    for name, tool in client.tools.items():
                        params = getattr(tool, 'parameters', {})
                        self._tools_list.append((
                            name,
                            tool,
                            params,
                        ))
                    mcp_tools += len(client.tools)

        self._count.setText(f"{mcp_tools} outils • {mcp_servers} serveurs")

        # Remplir la grille
        for i, (name, _, _) in enumerate(self._tools_list):
            card = ToolCard(name, "", server="NURU")
            self._grid.addWidget(card, i // 3, i % 3)

        if not self._tools_list:
            placeholder = QLabel("Aucun outil MCP enregistré")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 11pt;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(placeholder, 0, 0, 1, 3)

        # Info connexions
        clients = []
        if self._engine and self._engine.mcp_client:
            client = self._engine.mcp_client
            if hasattr(client, 'connections'):
                for c in client.connections:
                    transport = getattr(c, 'transport', '?')
                    if hasattr(transport, 'name'):
                        transport = transport.name
                    status = "✓" if getattr(c, 'enabled', False) else "○"
                    clients.append(f"{status} {getattr(c, 'name', '?')} ({transport})")

        if clients:
            self._conn_info.setText("Serveurs externes : " + " | ".join(clients))
        elif mcp_tools > 0:
            self._conn_info.setText("✓ Serveur MCP local actif")
        else:
            self._conn_info.setText("Aucun serveur MCP disponible")
