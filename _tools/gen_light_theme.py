#!/usr/bin/env python3
"""Génère styles_light.qss — conversion couleurs one-pass (pas de chaînage)."""
import re
from pathlib import Path

base = Path(__file__).parent.parent / "src" / "ui"
dark_path = base / "styles.qss"
light_path = base / "styles_light.qss"

dark_css = dark_path.read_text(encoding="utf-8")

color_map = {
    # Fonds
    "#0D0D12": "#FFFFFF",
    "#0F0F14": "#F5F5F8",
    "#12121C": "#FAFAFC",
    # Hover / surfaces
    "#1A1A24": "#EAEAF0",
    "#1A1A28": "#E8E8F4",
    "#1C1C26": "#E0E0E8",
    "#1C1C2A": "#E0E0E8",
    "#1E1E28": "#E8E8F0",
    "#252530": "#D0D0D8",
    "#35354A": "#B0B0C0",
    "#3A3A4E": "#B0B0C0",
    # Textes
    "#E5E5EC": "#1A1A2E",
    "#C0C0D0": "#3A3A4E",
    "#D0D0DC": "#3A3A4E",
    "#A0A0B8": "#5A5A6E",
    "#8A8AA0": "#6A6A7E",
    "#7A7A8E": "#6A6A7E",
    "#7A8A9E": "#7A7A8E",
    "#7A8cff": "#6366f1",
    "#6A6A7E": "#8A8A9E",
    "#5A5A6E": "#8A8A9E",
    "#B0B0C4": "#4A4A5E",
    # Accents
    "#818cf8": "#6366f1",
    "#22C55E": "#16A34A",
    "#F59E0B": "#D97706",
    "#EF4444": "#DC2626",
}

def replace_color(match: re.Match) -> str:
    color = match.group(0).upper()
    return color_map.get(color, match.group(0))

light_css = re.sub(r'#[0-9a-fA-F]{6}', replace_color, dark_css)

# Update header
light_css = light_css.replace("Midnight Indigo", "Dawn Alabaster")
light_css = light_css.replace("sombre, élégant", "clair, élégant")
light_css = light_css.replace("#0D0D12 fond", "#FFFFFF fond")

light_path.write_text(light_css, encoding="utf-8")

# Stats
nine_px = len(re.findall(r'font-size: 9px', light_css))
remaining = [c for c in color_map if c != "#818cf8" and c in light_css]
print(f"✓ styles_light.qss : {len(light_css)} chars, {light_css.count(chr(10))} lignes")
print(f"✓ font-size: 9px restant: {nine_px}")
print(f"✓ Couleurs sombres résiduelles: {len(remaining)}" + (f" ({remaining[:3]}...)" if remaining else ""))
