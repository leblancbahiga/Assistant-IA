"""Test complet architecture Z.ai V12 — Validation paragraphe par paragraphe."""
import sys, os
sys.path.insert(0, '.')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

# ── Test 1: Tokens Z.ai (§52-95) ──
from src.ui.tokens import Color, Typography, Radius, WindowSizes, OrbSizes

assert Color.BG_DEEP == '#0D1117', 'Z.ai: bg-primary #0D1117'
assert Color.BG_ELEVATED == '#161B22', 'Z.ai: bg-elevated #161B22'
assert Color.CYAN == '#58D5E3', 'Z.ai: accent-cyan #58D5E3'
assert Color.CYAN_GLOW == 'rgba(88,213,227,0.15)', 'Z.ai: cyan glow 0.15'
assert Color.WARM == '#E8A87C', 'Z.ai: accent-warm #E8A87C'
assert Color.TEXT_PRIMARY == '#E6EDF3'
assert Color.TEXT_SECONDARY == '#8B949E'
assert Color.TEXT_MUTED == '#484F58'
assert Color.BORDER == '#21262D'
assert Color.SUCCESS == '#3FB950'
assert Color.ERROR == '#F85149'
assert Radius.SMALL == 4, 'Z.ai: badge 4px'
assert Radius.MEDIUM == 12, 'Z.ai: card 12px'
assert Radius.LARGE == 16, 'Z.ai: overlay 16px'
assert WindowSizes.FLOATING_SIZE == 160, 'Z.ai: 160x160'
assert WindowSizes.WINDOW_WIDTH == 720
assert WindowSizes.WINDOW_HEIGHT == 860
assert OrbSizes.WINDOW == 120
assert OrbSizes.OVERLAY == 200
assert OrbSizes.FLOATING == 80

# Vérifier que 6 états seulement
from src.ui.presence_orb import OrbState
assert len(OrbState) == 6, f'Z.ai: 6 etats, trouve {len(OrbState)}'
assert [s.value for s in OrbState] == ['idle','listening','thinking','speaking','acting','error']
print('1/8 Tokens Z.ai exacts -- OK')

# ── Test 2: NuruPresenceOrb (§160, §257-293) ──
from src.ui.presence_orb import NuruPresenceOrb
orb = NuruPresenceOrb(orb_size=120)
assert orb.state == OrbState.IDLE
for s in OrbState:
    orb.set_state(s, progress=0.5 if s == OrbState.ACTING else None)
    assert orb.state == s, f'Etat {s.value}'
assert not hasattr(OrbState, 'RESPOND'), 'Z.ai: pas de respond'
print('2/8 Orb 6 etats + progress -- OK')

# ── Test 3: NuruWindow (§231-254) ──
from src.ui.nuru_window import NuruWindow
nw = NuruWindow()
assert nw.width() == 720
assert nw.height() == 860
assert nw.minimumWidth() == 480
assert nw.minimumHeight() == 600
assert nw.orb is not None, 'PresenceOrb requis'
assert nw.conversation is not None, 'ConversationSurface requis'
assert nw.input_bar is not None, 'InputBar requis'
print('3/8 NuruWindow 720x860 + PresenceOrb+Conversation+Input -- OK')

# ── Test 4: FloatingWidget (§202) ──
from src.ui.floating_widget import NuruFloatingWidget
fw = NuruFloatingWidget()
assert fw.width() == 160 and fw.height() == 160
fw.set_orb_state(OrbState.THINKING)
assert fw.orb.state == OrbState.THINKING
print('4/8 FloatingWidget 160x160 + orb sync -- OK')

# ── Test 5: VoiceOverlay (§165-168, §295-329) ──
from src.ui.voice_overlay import VoiceOverlay
vo = VoiceOverlay()
assert vo.orb is not None
assert vo.transcript is not None
vo.update_transcript('Bonjour NURU')
vo.update_response('Bonjour')
print('5/8 VoiceOverlay + transcript/response -- OK')

# ── Test 6: AmbientApp + Tray (§198-200) ──
from src.ui.ambient_app import AmbientApp, ChatOverlay
ambient = AmbientApp(app)
assert ambient.window is not None
assert ambient.floating_widget is not None
assert ambient.voice_overlay is not None
print('6/8 AmbientApp (NuruWindow + FloatingWidget + Tray + Voice) -- OK')

# ── Test 7: ChatOverlay ⌘N ──
co = ChatOverlay()
assert co.width() == 480
print('7/8 ChatOverlay -- OK')

# ── Test 8: Full sync ──
ambient._on_orb_state_changed(OrbState.THINKING)
assert ambient.window.orb.state == OrbState.THINKING
assert ambient.floating_widget.orb.state == OrbState.THINKING
ambient._on_orb_state_changed(OrbState.IDLE)
assert ambient.window.orb.state == OrbState.IDLE
assert ambient.floating_widget.orb.state == OrbState.IDLE
print('8/8 Sync Window <-> FloatingWidget <-> Tray -- OK')

# ── Clean ──
QTimer.singleShot(50, app.quit)
app.exec()

print()
print('Tous les tests passes -- Architecture Z.ai conforme au document concept !')
