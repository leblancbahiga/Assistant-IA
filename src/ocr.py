"""OCR Fallback pour NURU — PDF scannés non indexables sinusoïde.

Détecte les PDF sans texte extractible et applique Tesseract OCR.
Dépendances optionnelles : pytesseract, pdf2image, Pillow.
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.warning("⚠️ OCR désactivé : installer pytesseract + pdf2image")


def is_scanned_pdf(filepath: str | Path, min_pages: int = 1) -> bool:
    """Détecte si un PDF est scanné (sans texte extractible).

    Vérifie si le PDF a du texte extractible. Si moins de 50 caractères
    pour un document de + de 1 page, c'est probablement un scan.
    """
    if not HAS_OCR:
        return False
    try:
        import PyPDF2
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if len(reader.pages) < min_pages:
                return False
            total_text = ""
            for page in reader.pages:
                total_text += page.extract_text() or ""
            # Si moins de 50 chars pour + de 1 page → scan
            return len(total_text.strip()) < 50
    except Exception:
        # Si on ne peut pas lire le PDF → probablement scanné
        return True


def ocr_pdf(filepath: str | Path, lang: str = "fra+eng") -> Optional[str]:
    """Extrait le texte d'un PDF scanné via Tesseract OCR.

    Args:
        filepath: Chemin du PDF
        lang: Langues Tesseract (défaut: français + anglais)

    Returns:
        Texte extrait, ou None si échec
    """
    if not HAS_OCR:
        logger.warning("⚠️ OCR impossible : pytesseract ou pdf2image non installé")
        return None

    try:
        logger.info(f"📄 OCR: conversion {Path(filepath).name} en images...")
        images = convert_from_path(filepath, dpi=300)

        all_text = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang=lang)
            all_text.append(text)
            logger.info(f"  Page {i+1}/{len(images)}: {len(text)} chars extraits")

        result = "\n\n".join(all_text)
        logger.info(f"✅ OCR terminé: {len(result)} chars extraits")
        return result

    except Exception as e:
        logger.error(f"❌ OCR échoué: {e}")
        return None


def ocr_fallback(filepath: str | Path, original_content: str = "") -> str:
    """Point d'entrée : OCR si PDF scanné, sinon retourne le contenu original.

    Args:
        filepath: Chemin du fichier PDF
        original_content: Texte déjà extrait (sera utilisé si non vide)

    Returns:
        Texte extrait (OCR ou original)
    """
    path = Path(filepath)

    # Seulement pour les PDF
    if path.suffix.lower() != ".pdf":
        return original_content

    # Si le contenu original est déjà substantiel, pas besoin d'OCR
    if len(original_content.strip()) > 100:
        return original_content

    # Détection rapide : extension .pdf scanné ?
    if not is_scanned_pdf(filepath):
        return original_content

    logger.info(f"🔍 PDF scanné détecté: {path.name} — lancement OCR...")
    ocr_text = ocr_pdf(filepath)

    if ocr_text and len(ocr_text.strip()) > 20:
        return ocr_text

    # Fallback : garder le contenu original même s'il est pauvre
    logger.warning(f"⚠️ OCR n'a rien extrait de {path.name}, garde l'original")
    return original_content
