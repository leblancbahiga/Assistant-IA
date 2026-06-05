"""
Conversations Page — Historique des conversations passées.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QScrollArea, QPushButton, QLineEdit)
from PySide6.QtCore import Qt, Signal


class ConversationCard(QFrame):
    clicked = Signal(int)
    
    def __init__(self, conv_id, role, content, timestamp, parent=None):
        super().__init__(parent)
        self.conv_id = conv_id
        self.setObjectName("ConversationCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)
        header = QHBoxLayout()
        role_icon = "👤" if role == "user" else "🤖"
        role_label = QLabel(f"{role_icon}  {role.upper()}")
        color = '#00F2FF' if role == 'user' else '#8B5CF6'
        role_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        header.addWidget(role_label)
        header.addStretch()
        header.addWidget(time_label)
        layout.addLayout(header)
        preview = content[:120] + "..." if len(content) > 120 else content
        preview_label = QLabel(preview)
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        layout.addWidget(preview_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.conv_id)
        super().mousePressEvent(event)


class ConversationsPage(QWidget):
    def __init__(self, memory_store=None, parent=None):
        super().__init__(parent)
        self.memory_store = memory_store
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        header = QHBoxLayout()
        title = QLabel("💬  CONVERSATIONS")
        title.setObjectName("PageTitle")
        btn_refresh = QPushButton("↻  Actualiser")
        btn_refresh.setObjectName("GhostButton")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.load_conversations)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_refresh)
        layout.addLayout(header)
        
        stats_frame = QFrame()
        stats_frame.setObjectName("Panel")
        stats_frame.setFixedHeight(50)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 8, 15, 8)
        self.stat_total = QLabel("Total : 0")
        self.stat_total.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        self.stat_user = QLabel("👤 Utilisateur : 0")
        self.stat_user.setStyleSheet("color: #00F2FF; font-size: 13px;")
        self.stat_nuru = QLabel("🤖 NURU : 0")
        self.stat_nuru.setStyleSheet("color: #8B5CF6; font-size: 13px;")
        stats_layout.addWidget(self.stat_total)
        stats_layout.addStretch()
        stats_layout.addWidget(self.stat_user)
        stats_layout.addWidget(self.stat_nuru)
        layout.addWidget(stats_frame)
        
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
        
        self._add_empty_label()
    
    def _add_empty_label(self):
        lbl = QLabel("Aucune conversation pour le moment.\nCommencez à discuter dans la Console !")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #4B5563; font-size: 14px; padding: 40px;")
        self.container_layout.addWidget(lbl)
    
    def load_conversations(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.memory_store:
            lbl = QLabel("⚠ MemoryStore non connecté")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #F59E0B; font-size: 14px; padding: 40px;")
            self.container_layout.addWidget(lbl)
            return
        
        try:
            history = self.memory_store.get_recent_history(limit=50)
            if not history:
                self._add_empty_label()
                return
            
            user_count = sum(1 for h in history if h.get("role") == "user")
            nuru_count = len(history) - user_count
            self.stat_total.setText(f"Total : {len(history)}")
            self.stat_user.setText(f"👤 Utilisateur : {user_count}")
            self.stat_nuru.setText(f"🤖 NURU : {nuru_count}")
            
            for i, msg in enumerate(reversed(history)):
                card = ConversationCard(i, msg.get("role", "?"), msg.get("content", ""), msg.get("timestamp", ""))
                self.container_layout.addWidget(card)
        except Exception as e:
            lbl = QLabel(f"Erreur : {str(e)}")
            lbl.setStyleSheet("color: #EF4444; padding: 20px;")
            self.container_layout.addWidget(lbl)
    
    def showEvent(self, event):
        super().showEvent(event)
        self.load_conversations()
