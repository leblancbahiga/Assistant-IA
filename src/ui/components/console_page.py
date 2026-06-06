"""
Console Page V4.0 — Vue principale du chat NURU avec cartes de sources.
Support de formatage riche : listes, citations, code, tableaux.
"""
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QFrame, QScrollArea, QLineEdit, QPushButton)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QTextCharFormat, QTextCursor
from src.ui.components.chat_bubble import ChatBubble


class ConsolePage(QWidget):
    """Page Console V4.0 : Chat interactif + cartes de sources."""

    query_submitted = Signal(str)
    clear_requested = Signal()
    web_search_toggled = Signal(bool)
    voice_toggled = Signal()  # V4.5 : Mode vocal (microphone)
    # V4.5 Phase 4 : Feedback utilisateur
    feedback_received = Signal(str, str, str)  # (vote: 'up'|'down', message, query)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._web_search_enabled = False
        self._sources = []
        self._last_query = ""
        self._current_cot: QFrame = None  # V6 : Zone Chain of Thought
        self._last_assistant_bubble: ChatBubble = None  # Dernière bulle assistant
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)
        
        # Chat Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(15)  # More spacing between bubbles
        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area)
        
        # ─── SOURCES BAR ───
        self.sources_frame = QFrame()
        self.sources_frame.setObjectName("SourcesBar")
        self.sources_frame.setVisible(False)
        self.sources_layout = QHBoxLayout(self.sources_frame)
        self.sources_layout.setContentsMargins(8, 4, 8, 4)
        self.sources_layout.setSpacing(6)
        
        self.sources_title = QLabel("📎 SOURCES (0)")
        self.sources_title.setObjectName("PanelTitle")
        self.sources_layout.addWidget(self.sources_title)
        self.sources_layout.addStretch()
        layout.addWidget(self.sources_frame)
        
        # ─── INPUT AREA ───
        input_wrapper = QWidget()
        input_wrapper_layout = QVBoxLayout(input_wrapper)
        input_wrapper_layout.setContentsMargins(0, 0, 0, 10)
        
        input_container = QFrame()
        input_container.setObjectName("InputFrame") # Matching QSS
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(15, 8, 15, 8)
        input_layout.setSpacing(10)
        
        btn_attach = QPushButton("+")
        btn_attach.setObjectName("AttachButton")
        btn_attach.setFixedSize(32, 32)
        btn_attach.setCursor(Qt.PointingHandCursor)
        input_layout.addWidget(btn_attach)
        
        self.input_field = QLineEdit()
        self.input_field.setObjectName("ChatInput")
        self.input_field.setPlaceholderText("Posez une question sur vos documents (ex: YARID, Palabek, compétences...)")
        self.input_field.returnPressed.connect(self._on_submit)
        input_layout.addWidget(self.input_field, stretch=1)
        
        # Microphone pour le mode vocal
        self.btn_mic = QPushButton("🎤")
        self.btn_mic.setObjectName("VoiceButton")
        self.btn_mic.setFixedSize(32, 32)
        self.btn_mic.setCursor(Qt.PointingHandCursor)
        self.btn_mic.setCheckable(True)
        self.btn_mic.clicked.connect(self.voice_toggled.emit)
        input_layout.addWidget(self.btn_mic)
        
        self.btn_web = QPushButton("🌐 Recherche Web")
        self.btn_web.setObjectName("WebSearchBtn")
        self.btn_web.setCheckable(True)
        self.btn_web.setFixedHeight(32)
        self.btn_web.setCursor(Qt.PointingHandCursor)
        self.btn_web.clicked.connect(self._toggle_web_search)
        input_layout.addWidget(self.btn_web)
        
        btn_send = QPushButton("➤")
        btn_send.setObjectName("SendButton")
        btn_send.setFixedSize(36, 36)
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.clicked.connect(self._on_submit)
        input_layout.addWidget(btn_send)
        
        input_wrapper_layout.addWidget(input_container)
        
        hint = QLabel("Entrée = Envoyer  •  Shift+Entrée = Nouvelle ligne")
        hint.setObjectName("InputHint")
        hint.setAlignment(Qt.AlignCenter)
        input_wrapper_layout.addWidget(hint)
        
        layout.addWidget(input_wrapper)
        
        # Indicateur d'écoute vocale
        self.listening_label = QLabel("🎙 NURU écoute... (cliquez 🔴 pour arrêter, auto-stop 15s)")
        self.listening_label.setObjectName("ListeningLabel")
        self.listening_label.setAlignment(Qt.AlignCenter)
        self.listening_label.setVisible(False)
        layout.addWidget(self.listening_label)

        
        # Indicateur d'écoute vocale
        self.listening_label = QLabel("🎙  NURU écoute... (cliquez 🔴 pour arrêter, auto-stop 15s)")
        self.listening_label.setObjectName("ListeningLabel")
        self.listening_label.setAlignment(Qt.AlignCenter)
        self.listening_label.setVisible(False)
        layout.addWidget(self.listening_label)
    
    # ─── PUBLIC API ───

    def add_message(self, sender: str, text: str, is_user: bool, rag_score: float = None) -> ChatBubble:
        """Add a message with rich text formatting support and optional RAG score."""
        bubble = ChatBubble(sender, "", is_user=is_user, rag_score=rag_score)

        # Enable rich text formatting in the bubble's message area
        if hasattr(bubble, 'msg_text'):
            formatted_text = self._format_message_text(text)
            bubble.msg_text.setHtml(formatted_text)
            bubble.msg_text.verticalScrollBar().setValue(
                bubble.msg_text.verticalScrollBar().maximum()
            )
        else:
            bubble = ChatBubble(sender, text, is_user=is_user, rag_score=rag_score)

        self.chat_layout.addWidget(bubble)
        self._scroll_to_bottom()

        # V4.5 Phase 4 : Connecter le feedback des messages assistant
        if not is_user:
            bubble.feedback_given.connect(lambda v, m: self.feedback_received.emit(v, m, self._last_query))
            self._last_assistant_bubble = bubble

        return bubble

    def update_last_assistant_rag(self, rag_score: float):
        """Met à jour le badge RAG sur la dernière bulle assistant."""
        if self._last_assistant_bubble:
            self._last_assistant_bubble.set_rag_score(rag_score)

    def get_last_assistant_bubble(self):
        """Retourne la dernière bulle assistant (pour mise à jour)."""
        return self._last_assistant_bubble

    def add_cot(self, title: str = "Analyse du système..."):
        """V6 : Ajoute une zone Chain of Thought repliable avant la réponse."""
        cot_frame = QFrame()
        cot_frame.setObjectName("CoTFrame")
        cot_frame.setStyleSheet("""
            #CoTFrame {
                background-color: rgba(255, 176, 0, 0.05);
                border: 1px solid rgba(255, 176, 0, 0.2);
                border-left: 3px solid #FFB000;
                border-radius: 6px;
                margin: 4px 20px 4px 50px;
                padding: 8px;
            }
        """)

        cot_layout = QVBoxLayout(cot_frame)
        cot_layout.setSpacing(4)

        # Header cliquable
        header_layout = QHBoxLayout()
        toggle_btn = QPushButton("▶")
        toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #FFB000; border: none;
                font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { color: #39FF14; }
        """)
        toggle_btn.setFixedSize(20, 20)
        toggle_btn.setCursor(Qt.PointingHandCursor)

        cot_title = QLabel(f"🧠 {title}")
        cot_title.setStyleSheet("color: #FFB000; font-size: 10px; font-weight: bold;")

        header_layout.addWidget(toggle_btn)
        header_layout.addWidget(cot_title)
        header_layout.addStretch()
        cot_layout.addLayout(header_layout)

        # Contenu (caché par défaut)
        self._cot_content = QLabel("Analyse en cours...")
        self._cot_content.setStyleSheet("color: #A78BFA; font-size: 11px; padding-left: 24px;")
        self._cot_content.setWordWrap(True)
        self._cot_content.setVisible(False)
        cot_layout.addWidget(self._cot_content)

        # Toggle
        toggle_btn.clicked.connect(
            lambda: self._cot_content.setVisible(not self._cot_content.isVisible())
        )

        self.chat_layout.addWidget(cot_frame)
        self._scroll_to_bottom()

        # Stocker pour mise à jour
        self._current_cot = cot_frame
        return cot_frame

    def update_cot(self, text: str):
        """V6 : Met à jour le contenu de la zone CoT."""
        if hasattr(self, '_cot_content') and self._cot_content:
            current = self._cot_content.text()
            if current == "Analyse en cours...":
                self._cot_content.setText(text)
            else:
                self._cot_content.setText(current + "\n" + text)

    def _format_message_text(self, text: str) -> str:
        """Convert plain text with special markers to HTML for rich display"""
        if not text:
            return ""
        
        # Escape HTML first
        escaped = (text.replace("&", "&amp")
                   .replace("<", "&lt")
                   .replace(">", "&gt")
                   .replace('"', "&quot")
                   .replace("'", "&#x27"))
        
        # Process special formatting markers
        
        # 1. Source citations: [Source: ...] -> blue clickable links
        # Pattern: [Source: text] or [Source: text (url)]
        def replace_source(match):
            content = match.group(1)
            # Check if there's a URL in parentheses
            url_match = re.search(r'\((https?://[^)]+)\)', content)
            if url_match:
                url = url_match.group(1)
                display_text = content.replace(f'({url})', '').strip()
                return f'<a href="{url}" style="color: #0A84FF; text-decoration: underline;">[Source: {display_text}]</a>'
            else:
                return f'<span style="color: #0A84FF;">[Source: {content}]</span>'
        
        escaped = re.sub(r'\[Source:\s*([^\]]+)\]', replace_source, escaped)
        
        # 2. Code blocks: ```language\ncode\n``` -> styled blocks
        def replace_code_block(match):
            language = match.group(1).strip()
            code = match.group(2)
            # Simple syntax highlighting for common languages
            if language.lower() == 'php':
                # Basic PHP highlighting
                code = re.sub(r'(\b(class|function|public|private|protected|static|return|if|else|for|while|new)\b)', 
                            r'<span style="color: #FF9F0A;">\1</span>', code)
                code = re.sub(r'(\$[a-zA-Z_][a-zA-Z0-9_]*)', 
                            r'<span style="color: #5AC8FA;">\1</span>', code)
                code = re.sub(r'(".*?")', 
                            r'<span style="color: #FFCC66;">\1</span>', code)
            return f'<div style="background-color: rgba(0,0,0,0.2); border-left: 3px solid #0A84FF; padding: 8px 12px; margin: 4px 0; font-family: \'SF Mono\', monospace; font-size: 13px; line-height: 1.4; color: #E5E5E5;">{code}</div>'
        
        escaped = re.sub(r'```(\w*)\n([\s\S]*?)\n```', replace_code_block, escaped, flags=re.MULTILINE)
        
        # 3. Inline code: `code` -> styled inline
        escaped = re.sub(r'`([^`]+)`', 
                        r'<span style="background-color: rgba(0,0,0,0.1); padding: 2px 4px; border-radius: 4px; font-family: \'SF Mono\', monospace; font-size: 12px;">\1</span>', escaped)
        
        # 4. Bold text: **text** -> bold
        escaped = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped)
        
        # 5. Italic text: *text* -> italic
        escaped = re.sub(r'\*(.*?)\*', r'<em>\1</em>', escaped)
        
        # 6. Tables: simple markdown-style table formatting
        lines = escaped.split('\n')
        processed_lines = []
        in_table = False
        
        for line in lines:
            # Detect table header: |---|---|---|
            if re.match(r'^\s*\|.*\|.*\|\s*$', line) and '---' in line:
                in_table = True
                # Add table start
                processed_lines.append('<table style="width: 100%; border-collapse: collapse; margin: 8px 0;">')
                continue
            elif in_table and re.match(r'^\s*\|.*\|.*\|\s*$', line):
                # Table row
                cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last
                if not processed_lines or not processed_lines[-1].startswith('<tr>'):
                    # First data row after header - treat as header
                    processed_lines.append('<thead><tr>')
                    for cell in cells:
                        processed_lines.append(f'<th style="border: 1px solid rgba(255,255,255,0.1); padding: 8px 12px; '
                                               f'text-align: left; background-color: rgba(10,132,255,0.1);">{cell}</th>')
                    processed_lines.append('</tr></thead><tbody>')
                else:
                    # Regular data row
                    processed_lines.append('<tr>')
                    for cell in cells:
                        processed_lines.append(f'<td style="border: 1px solid rgba(255,255,255,0.1); padding: 8px 12px; '
                                               f'text-align: left; background-color: rgba(45,45,50,0.3);">{cell}</td>')
                    processed_lines.append('</tr>')
                continue
            elif in_table and not re.match(r'^\s*\|.*\|.*\|\s*$', line):
                # End of table
                in_table = False
                processed_lines.append('</tbody></table>')
            
            if not in_table:
                processed_lines.append(line)
        
        escaped = '\n'.join(processed_lines)
        
        # 7. Bullet points: lines starting with - or •
        lines = escaped.split('\n')
        processed_lines = []
        in_list = False
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- ') or stripped.startswith('• ') or stripped.startswith('* '):
                if not in_list:
                    processed_lines.append('<ul style="margin: 8px 0; padding-left: 20px;">')
                    in_list = True
                # Remove the bullet marker
                content = stripped[2:] if len(stripped) > 2 else stripped
                processed_lines.append(f'<li style="margin: 4px 0; line-height: 1.5;">{content}</li>')
            else:
                if in_list:
                    processed_lines.append('</ul>')
                    in_list = False
                processed_lines.append(line)
        
        if in_list:
            processed_lines.append('</ul>')
        
        escaped = '\n'.join(processed_lines)
        
        # 8. Line breaks
        escaped = escaped.replace('\n', '<br>')
        
        return f'<div style="line-height: 1.6; color: #E5E5E5;">{escaped}</div>'
    
    def scroll_to_bottom(self):
        self._scroll_to_bottom()
    
    def set_sources(self, sources: list):
        """Met à jour la barre de sources avec les documents trouvés."""
        while self.sources_layout.count() > 2:
            item = self.sources_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        
        self._sources = sources
        self.sources_title.setText(f"📎 SOURCES ({len(sources)})")
        
        for src in sources[:5]:
            name = src.get("name", "?")
            score = src.get("score", 0.0)
            ext = name.rsplit(".", 1)[-1].upper() if "." in name else "TXT"
            
            badge = QFrame()
            badge.setObjectName("SourceBadge")
            badge_layout = QHBoxLayout(badge)
            badge_layout.setContentsMargins(8, 4, 8, 4)
            badge_layout.setSpacing(5)
            
            icon = QLabel("📄")
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("color: #D1D5DB; font-size: 11px;")
            score_lbl = QLabel(f"Score : {score:.2f}")
            score_lbl.setStyleSheet("color: #6B7280; font-size: 9px;")
            ext_badge = QLabel(ext)
            ext_badge.setObjectName("ExtBadge")
            
            badge_layout.addWidget(icon)
            info_layout = QVBoxLayout()
            info_layout.setSpacing(0)
            info_layout.addWidget(name_lbl)
            info_layout.addWidget(score_lbl)
            badge_layout.addLayout(info_layout)
            badge_layout.addWidget(ext_badge)
            
            self.sources_layout.insertWidget(self.sources_layout.count() - 1, badge)
        
        self.sources_frame.setVisible(len(sources) > 0)
    
    def set_listening(self, active: bool):
        self.listening_label.setVisible(active)
        # Retour visuel sur le bouton mic
        self.btn_mic.setChecked(active)
        self.btn_mic.setText("🔴" if active else "🎤")
        self.btn_mic.setToolTip("Arrêter l'écoute" if active else "Activer le mode vocal")
    
    def clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._last_assistant_bubble = None
    
    # ─── PRIVATE ───
    
    def _on_submit(self):
        query = self.input_field.text().strip()
        if query:
            self._last_query = query
            self.input_field.clear()
            self.query_submitted.emit(query)
    
    def _on_clear(self):
        self.clear_chat()
        self.clear_requested.emit()
    
    def _toggle_web_search(self):
        self._web_search_enabled = self.btn_web.isChecked()
        self.web_search_toggled.emit(self._web_search_enabled)
    
    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())
