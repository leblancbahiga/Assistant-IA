"""
Plugins Page — Gestion des plugins chargés.
"""
from pathlib import Path
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QScrollArea, QPushButton, QFileDialog,
                               QMessageBox)
from PySide6.QtCore import Qt


class PluginCard(QFrame):
    def __init__(self, name, description, active=True, version="1.0", parent=None):
        super().__init__(parent)
        self.plugin_name = name
        self.setObjectName("ConversationCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        icon = QLabel("🔌")
        icon.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon)
        
        info = QVBoxLayout()
        info.setSpacing(3)
        name_lbl = QLabel(f"{name}  v{version}")
        name_lbl.setStyleSheet("color: #F3F4F6; font-weight: bold; font-size: 14px;")
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        info.addWidget(name_lbl)
        info.addWidget(desc_lbl)
        layout.addLayout(info, stretch=1)
        
        # Active/Inactive toggle button
        self.active = active
        self.toggle_btn = QPushButton("● Actif" if active else "○ Inactif")
        color = "#10B981" if active else "#6B7280"
        self.toggle_btn.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; background: transparent; border: 1px solid {color}; padding: 4px 8px; border-radius: 4px;")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self.toggle_btn)

    def _toggle(self):
        self.active = not self.active
        color = "#10B981" if self.active else "#6B7280"
        self.toggle_btn.setText("● Actif" if self.active else "○ Inactif")
        self.toggle_btn.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; background: transparent; border: 1px solid {color}; padding: 4px 8px; border-radius: 4px;")


class PluginsPage(QWidget):
    def __init__(self, plugin_system=None, parent=None):
        super().__init__(parent)
        self.plugin_system = plugin_system
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        header = QHBoxLayout()
        title = QLabel("🔌  PLUGINS")
        title.setObjectName("PageTitle")

        btn_install = QPushButton("📦  Installer")
        btn_install.setObjectName("PrimaryButton")
        btn_install.setCursor(Qt.PointingHandCursor)
        btn_install.clicked.connect(self._install_plugin)

        btn_reload = QPushButton("↻  Recharger tous")
        btn_reload.setObjectName("GhostButton")
        btn_reload.setCursor(Qt.PointingHandCursor)
        btn_reload.clicked.connect(self._reload_all)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_install)
        header.addWidget(btn_reload)
        layout.addLayout(header)
        
        # Info
        info_frame = QFrame()
        info_frame.setObjectName("Panel")
        info_frame.setFixedHeight(50)
        il = QHBoxLayout(info_frame)
        il.setContentsMargins(15, 8, 15, 8)
        self.plugin_count = QLabel("0 plugins chargés")
        self.plugin_count.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        path_lbl = QLabel("📂 Dossier : plugins/")
        path_lbl.setStyleSheet("color: #6B7280; font-size: 12px;")
        il.addWidget(self.plugin_count)
        il.addStretch()
        il.addWidget(path_lbl)
        layout.addWidget(info_frame)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignTop)
        self.container_layout.setSpacing(8)
        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)
        
        self._show_empty()
    
    def _show_empty(self):
        lbl = QLabel("Aucun plugin installé.\nPlacez vos plugins dans le dossier plugins/ et rechargez.")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #4B5563; font-size: 14px; padding: 40px;")
        lbl.setObjectName("empty_plugins")
        self.container_layout.addWidget(lbl)
    
    def _install_plugin(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier de plugin")
        if folder and self.plugin_system:
            name = Path(folder).name
            dest = self.plugin_system.plugins_dir / name
            if not dest.exists():
                import shutil
                shutil.copytree(folder, dest)
                self.plugin_system.load_plugin(name)
                self.load_plugins()
                QMessageBox.information(self, "Plugin installé", f"✅ {name} installé avec succès.")
            else:
                QMessageBox.warning(self, "Erreur", f"Le plugin {name} existe déjà.")

    def load_plugins(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.plugin_system:
            self._show_empty()
            return
        
        plugins = self.plugin_system.loaded_plugins
        if not plugins:
            self._show_empty()
            self.plugin_count.setText("0 plugins chargés")
            return

        self.plugin_count.setText(f"{len(plugins)} plugin{'s' if len(plugins) > 1 else ''} chargé{'s' if len(plugins) > 1 else ''}")
        for name, plugin in plugins.items():
            desc = getattr(plugin, 'description', 'Pas de description')
            version = getattr(plugin, 'version', '1.0')
            card = PluginCard(name, desc, active=True, version=version)
            self.container_layout.addWidget(card)
    
    def _reload_all(self):
        if self.plugin_system:
            self.plugin_system.load_all()
        self.load_plugins()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.load_plugins()
