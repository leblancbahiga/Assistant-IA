"""Test complet architecture Z.ai V12 — Validation paragraphe par paragraphe.
Converted from standalone script to pytest tests (2026-06-24)."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import sys
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    """QApplication unique pour tout le module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestZaiTokens:
    """Test 1: Tokens Z.ai (§52-95) — DM-1 Deep Cyan."""

    def test_color_tokens(self):
        from src.ui.tokens import Color
        assert Color.BG_DEEP == '#0A0E17'
        assert Color.BG_ELEVATED == '#151B26'
        assert Color.CYAN == '#00D4FF'
        assert Color.CYAN_GLOW == 'rgba(0, 212, 255, 0.15)'
        assert Color.WARM == '#FFB800'
        assert Color.TEXT_PRIMARY == '#E8ECF1'
        assert Color.TEXT_SECONDARY == '#8B95A5'
        assert Color.TEXT_MUTED == '#4A5568'
        assert Color.BORDER == 'rgba(0, 212, 255, 0.12)'
        assert Color.SUCCESS == '#00E599'
        assert Color.ERROR == '#FF4D6A'

    def test_radius_tokens(self):
        from src.ui.tokens import Radius
        assert Radius.SMALL == 4
        assert Radius.MEDIUM == 8
        assert Radius.LARGE == 12

    def test_window_sizes(self):
        from src.ui.tokens import WindowSizes, OrbSizes
        assert WindowSizes.FLOATING_SIZE == 260
        assert WindowSizes.WINDOW_WIDTH == 720
        assert WindowSizes.WINDOW_HEIGHT == 860
        assert OrbSizes.WINDOW == 120
        assert OrbSizes.OVERLAY == 200
        assert OrbSizes.FLOATING == 80


class TestZaiOrbStates:
    """Orb states: 7 états (IDLE..SLEEP), pas de 'respond'."""

    def test_orb_state_enum(self):
        from src.ui.presence_orb import OrbState
        expected = ['IDLE', 'LISTENING', 'THINKING', 'SPEAKING', 'ACTING', 'ERROR', 'SLEEP']
        assert len(OrbState) == 7
        assert [s.name for s in OrbState] == expected


class TestZaiPresenceOrb:
    """Test 2: NuruPresenceOrb (§160, §257-293) via set_state/_state."""

    def test_orbitial_state_transitions(self, qapp):
        from src.ui.presence_orb import OrbState, NuruPresenceOrb
        orb = NuruPresenceOrb(orb_size=120)
        assert orb._state == OrbState.IDLE
        for s in OrbState:
            orb.set_state(s)
            assert orb._state == s
        orb.deleteLater()

    def test_orb_default_idle(self, qapp):
        from src.ui.presence_orb import NuruPresenceOrb, OrbState
        orb = NuruPresenceOrb(orb_size=120)
        assert orb._state == OrbState.IDLE
        orb.deleteLater()


class TestZaiNuruWindow:
    """Test 3: NuruWindow (§231-254)."""

    def test_window_dimensions(self, qapp):
        from src.ui.nuru_window import NuruWindow
        nw = NuruWindow()
        assert nw.width() == 720
        assert nw.height() == 860
        assert nw.minimumWidth() == 480
        assert nw.minimumHeight() == 600
        nw.deleteLater()

    def test_window_has_core_components(self, qapp):
        from src.ui.nuru_window import NuruWindow
        nw = NuruWindow()
        assert nw.orb is not None
        assert nw.conversation is not None
        assert nw.input_bar is not None
        nw.deleteLater()


class TestZaiFloatingWidget:
    """Test 4: FloatingWidget (§202) — dimensions et orb interne."""

    def test_dimensions(self, qapp):
        from src.ui.floating_widget import NuruFloatingWidget
        fw = NuruFloatingWidget()
        assert fw.width() == 260 and fw.height() == 180
        assert fw._mini_orb is not None
        fw.deleteLater()


class TestZaiVoiceOverlay:
    """Test 5: VoiceOverlay (§165-168, §295-329)."""

    def test_has_transcript_and_state(self, qapp):
        from src.ui.voice_overlay import VoiceOverlay
        vo = VoiceOverlay()
        assert vo._transcript is not None
        vo.update_transcript('Bonjour NURU')
        vo.update_state('speaking')
        vo.close()


class TestZaiAmbientApp:
    """Test 6-8: AmbientApp + sync (Mock tray+engine+show pour éviter blocage)."""

    @staticmethod
    def _make_ambient(qapp):
        """Crée un AmbientApp avec composants bloquants mockés."""
        from unittest.mock import patch, MagicMock
        from src.ui.ambient_app import AmbientApp
        with patch('src.ui.ambient_app.NURUTrayIcon') as mock_tray, \
             patch('src.core.conversation_engine.ConversationEngine.start'), \
             patch.object(AmbientApp, '_show_floating'), \
             patch.object(AmbientApp, '_setup_shortcuts'), \
             patch('src.ui.nuru_window.NuruWindow.show'):
            mock_tray_instance = MagicMock()
            mock_tray.return_value = mock_tray_instance
            mock_tray_instance.show_action = MagicMock()
            mock_tray_instance.voice_action = MagicMock()
            mock_tray_instance.widget_action = MagicMock()
            mock_tray_instance.pref_action = MagicMock()
            mock_tray_instance.quit_action = MagicMock()
            mock_tray_instance.tray = MagicMock()
            mock_tray_instance.set_state = MagicMock()
            return AmbientApp(qapp)

    def test_ambient_app_creates_components(self, qapp):
        amb = self._make_ambient(qapp)
        assert amb.window is not None
        assert amb.floating_widget is not None
        assert amb.voice_overlay is not None

    def test_orb_state_sync(self, qapp):
        """set_state() sur l'orb → _on_orb_state_changed reçoit le signal."""
        from src.ui.presence_orb import OrbState
        amb = self._make_ambient(qapp)
        # Déclencher via l'orb → signal state_changed → _on_orb_state_changed
        amb.window.orb.set_state(OrbState.THINKING)
        assert amb.window.orb._state == OrbState.THINKING
        # Le floating widget doit refléter l'état via setStatus
        assert amb._orb_state == OrbState.THINKING
        amb.window.orb.set_state(OrbState.IDLE)
        assert amb.window.orb._state == OrbState.IDLE
        assert amb._orb_state == OrbState.IDLE
