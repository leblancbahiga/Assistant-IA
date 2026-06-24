"""
Utilitaire de conversion Markdown → HTML pour les bulles de chat.

Utilise la bibliothèque ``markdown`` (Python-Markdown) avec extensions :
- fenced_code, tables, codehilite, nl2br

Fournit :
- ``MarkdownRenderer.render(text)`` → HTML stylisé pour Qt RichText
- ``MarkdownRenderer.strip_markdown(text)`` → texte brut sans markdown
- ``MarkdownRenderer.snippet(text, max_len)`` → extrait N premiers caractères sans markdown

Design system : thème sombre ``#0D1117``, ``#1A1A2E``, accents ``#818cf8``.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import markdown as _md_lib

    _MARKDOWN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MARKDOWN_AVAILABLE = False


# ── Style CSS réutilisable pour le HTML produit ──────────────────────────

_CODE_INLINE = (
    'code style="background:#1A1A2E;color:#E0E0E0;'
    'padding:1px 4px;border-radius:3px;font-size:12px;'
    'font-family:monospace;"'
)

_CODE_BLOCK = (
    'pre style="background:#0D1117;border:1px solid #2A2A4E;'
    'border-radius:6px;padding:12px;overflow-x:auto;font-size:12px;'
    'font-family:monospace;margin:6px 0;"'
)

_TABLE_STYLE = (
    'table style="border-collapse:collapse;width:100%;margin:8px 0;'
    'font-size:12px;"'
)
_TH_STYLE = (
    'th style="background:#1A1A2E;padding:6px 10px;'
    'border:1px solid #2A2A4E;color:#818cf8;font-weight:600;"'
)
_TD_STYLE = (
    'td style="padding:6px 10px;border:1px solid #2A2A4E;'
    'color:#E2E8F0;"'
)

_LINK_STYLE = (
    'a style="color:#818cf8;text-decoration:none;'
    'border-bottom:1px dotted #6366f1;"'
)

_PARAGRAPH_STYLE = 'p style="margin:4px 0;line-height:1.5;"'

_UL_STYLE = (
    'ul style="margin:4px 0;padding-left:20px;line-height:1.6;"'
)
_OL_STYLE = (
    'ol style="margin:4px 0;padding-left:20px;line-height:1.6;"'
)

_WRAPPER = (
    'div style="line-height:1.6;color:#E2E8F0;'
    'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,'
    'Helvetica,Arial,sans-serif;"'
)


class MarkdownRenderer:
    """Convertisseur Markdown → HTML pour l'interface de chat.

    Usage::

        html = MarkdownRenderer.render(markdown_text)
        plain = MarkdownRenderer.strip_markdown(markdown_text)
        snippet = MarkdownRenderer.snippet(markdown_text, max_len=200)
    """

    EXTENSIONS = [
        "fenced_code",
        "tables",
        "codehilite",
        "nl2br",
    ]
    EXTENSION_CONFIG = {
        "codehilite": {
            "css_class": "highlight",
            "guess_lang": False,
        },
    }

    # ── Render public ─────────────────────────────────────────────────

    @staticmethod
    def render(text: str) -> str:
        """Convertit le markdown *text* en HTML stylisé pour Qt RichText.

        Returns
        -------
        str
            HTML avec styles inline compatibles ``QLabel(RichText)``.
            Retourne ``\"\"`` si *text* est vide ou ``None``.
        """
        if not text:
            return ""

        if not _MARKDOWN_AVAILABLE:
            # Fallback : échappement HTML simple
            return MarkdownRenderer._fallback_html(text)

        # 1. Conversion markdown → HTML
        html = _md_lib.markdown(
            text,
            extensions=MarkdownRenderer.EXTENSIONS,
            extension_configs=MarkdownRenderer.EXTENSION_CONFIG,
        )

        # 2. Post-traitement : injecter nos styles inline
        html = MarkdownRenderer._inject_styles(html)

        # 3. Citations [N] → liens cliquables (après styles)
        html = MarkdownRenderer._linkify_citations(html)

        # 4. Wrapper final
        return f"<{_WRAPPER}>{html}</{_WRAPPER.split()[0]}>"

    # ── Utilitaires ───────────────────────────────────────────────────

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Supprime toute syntaxe markdown et retourne le texte brut.

        Utile pour la copie dans le presse-papier.
        """
        if not text:
            return ""

        # Enlever les blocs de code ```...```
        s = re.sub(r"```[\s\S]*?```", "", text)
        # Enlever le code inline `...`
        s = re.sub(r"`([^`]+)`", r"\1", s)
        # Enlever les images ![alt](url)
        s = re.sub(r"!\[.*?\]\(.*?\)", "", s)
        # Enlever les liens [text](url) → text
        s = re.sub(r"\[([^\]]*)\]\(.*?\)", r"\1", s)
        # Enlever le gras **...**
        s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
        # Enlever l'italique *...*
        s = re.sub(r"\*(.*?)\*", r"\1", s)
        # Enlever le ~~barré~~
        s = re.sub(r"~~(.*?)~~", r"\1", s)
        # Enlever les titres #
        s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
        # Enlever les listes -, *, +
        s = re.sub(r"^[\s]*[-*+]\s+", "", s, flags=re.MULTILINE)
        # Enlever les numbered lists
        s = re.sub(r"^[\s]*\d+\.\s+", "", s, flags=re.MULTILINE)
        # Enlever les sauts de table |
        s = re.sub(r"\|", " ", s)
        # Nettoyer les lignes de séparation de table
        s = re.sub(r"^[\s\-:]+\n", "", s, flags=re.MULTILINE)
        # Enlever les lignes horizontales
        s = re.sub(r"^---+$", "", s, flags=re.MULTILINE)
        # Enlever les sauts de ligne multiples
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    @staticmethod
    def snippet(text: str, max_len: int = 200) -> str:
        """Extrait les *max_len* premiers caractères sans markdown.

        Returns
        -------
        str
            Texte brut, tronqué à *max_len* caractères (sans couper un mot),
            suffixé par ``…`` si tronqué.
        """
        plain = MarkdownRenderer.strip_markdown(text)
        if len(plain) <= max_len:
            return plain
        # Tronquer au mot le plus proche
        truncated = plain[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            truncated = truncated[:last_space]
        return truncated.strip() + "…"

    # ── Méthodes privées ──────────────────────────────────────────────

    @staticmethod
    def _fallback_html(text: str) -> str:
        """Échappement HTML simple (fallback si markdown non installé)."""
        s = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        s = re.sub(r"`([^`]+)`", rf"<{_CODE_INLINE}>\1</code>", s)
        s = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.*?)\*", r"<em>\1</em>", s)
        s = s.replace("\n", "<br>")
        return f"<{_WRAPPER}>{s}</{_WRAPPER.split()[0]}>"

    @staticmethod
    def _inject_styles(html: str) -> str:
        """Injecte les styles inline dans les balises HTML produites par markdown.

        Remplace :
        - ``<p>``          → ``<p style="...">``
        - ``<ul>``         → ``<ul style="...">``
        - ``<ol>``         → ``<ol style="...">``
        - ``<table>``      → ``<table style="...">``
        - ``<th>``         → ``<th style="...">``
        - ``<td>``         → ``<td style="...">``
        - ``<a href=...>`` → ``<a style="..." href=...>``
        - ``<code>`` dans un ``<pre>`` → version bloc
        - ``<code>`` seules → version inline
        """
        # Ordre important : traiter <pre><code> avant <code> seul
        # <pre><code> → bloc
        html = re.sub(
            r"<pre><code(?:\s+class=\"([^\"]*)\")?>",
            lambda m: f"<{_CODE_BLOCK}><code>",
            html,
        )
        html = re.sub(r"</code></pre>", "</code></pre>", html)

        # <code> qui ne sont pas dans un <pre> → inline
        html = re.sub(
            r"(?<!<pre>)<code>((?!</code></pre>))",
            f"<{_CODE_INLINE}>",
            html,
        )

        # <p>
        html = re.sub(
            r"<p((?:\s+[^>]*)?)>",
            f"<{_PARAGRAPH_STYLE}>",
            html,
        )

        # <ul>
        html = re.sub(
            r"<ul((?:\s+[^>]*)?)>",
            f"<{_UL_STYLE}>",
            html,
        )

        # <ol>
        html = re.sub(
            r"<ol((?:\s+[^>]*)?)>",
            f"<{_OL_STYLE}>",
            html,
        )

        # <table>
        html = re.sub(
            r"<table((?:\s+[^>]*)?)>",
            f"<{_TABLE_STYLE}>",
            html,
        )

        # <th>
        html = re.sub(
            r"<th((?:\s+[^>]*)?)>",
            f"<{_TH_STYLE}>",
            html,
        )

        # <td>
        html = re.sub(
            r"<td((?:\s+[^>]*)?)>",
            f"<{_TD_STYLE}>",
            html,
        )

        # <a href="..."> — remplacer toute la balise
        html = re.sub(
            r'<a\s+href="([^"]*)"((?:\s+[^>]*)?)>',
            lambda m: f'<a href="{m.group(1)}" style="color:#818cf8;text-decoration:none;border-bottom:1px dotted #6366f1;">',
            html,
        )

        return html

    @staticmethod
    def _linkify_citations(html: str) -> str:
        """Convertit les marqueurs [N] en hyperliens cliquables.

        Exemple: ``[1]`` → ``<a href="citation:1" ...>[1]</a>``
        Protection des [N] déjà dans des balises <a> avant substitution.
        """
        def _replace(m: re.Match) -> str:
            num = m.group(1)
            return (
                f'<a href="citation:{num}" '
                f'style="color:#818cf8;text-decoration:none;'
                f'font-weight:600;border-bottom:1px dotted #6366f1;"'
                f' title="Source {num}">'
                f"[{num}]</a>"
            )
        # 1. Protéger les [N] déjà dans une balise <a>
        def _protect(m):
            return m.group(0).replace("[", "&#91;").replace("]", "&#93;")
        html = re.sub(r"<a[^>]*>.*?</a>", _protect, html)
        # 2. Lier les [N] non protégés
        html = re.sub(r"\[(\d+)\]", _replace, html)
        # 3. Restaurer les [N] protégés
        html = html.replace("&#91;", "[").replace("&#93;", "]")
        return html
