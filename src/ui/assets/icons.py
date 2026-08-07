"""
NURU V16 — SVG Icons.
Icônes vectorielles inline (zero dépendance) pour la Sidebar.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvg import QSvgRenderer

_STROKE = 'stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"'
_STROKE_FILL = f'stroke="currentColor" stroke-width="1.8" fill="currentColor" stroke-linecap="round" stroke-linejoin="round"'

ICONS: dict[str, str] = {
    "home": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" {_STROKE}/>'
        f'</svg>'
    ),
    "chat": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" {_STROKE}/>'
        f'</svg>'
    ),
    "documents": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" {_STROKE}/>'
        f'</svg>'
    ),
    "memory": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" {_STROKE}/>'
        f'</svg>'
    ),
    "agents": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" {_STROKE}/>'
        f'</svg>'
    ),
    "plugins": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" {_STROKE}/>'
        f'</svg>'
    ),
    "tools": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" {_STROKE}/>'
        f'  <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" {_STROKE}/>'
        f'</svg>'
    ),
    "models": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" {_STROKE}/>'
        f'</svg>'
    ),
    "dashboard": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" {_STROKE}/>'
        f'</svg>'
    ),
    "settings": (
        f'<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        f'  <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" {_STROKE}/>'
        f'  <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" {_STROKE}/>'
        f'</svg>'
    ),
}


def svg_icon(name: str, size: int = 20) -> QIcon:
    """Génère un QIcon à partir d'un SVG inline, coloré via QPalette."""
    raw = ICONS.get(name)
    if not raw:
        return QIcon()
    svg_bytes = raw.encode("utf-8")
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)
