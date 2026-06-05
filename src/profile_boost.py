"""NURU V6 — Profile Boost : booste les documents personnels de Leblanc.

Liste blanche des fichiers qui sont LES SIENS (CV, lettres de motivation, etc.).
Ces fichiers reçoivent un boost de score dans le RAG pour qu'ils apparaissent
en priorité par rapport aux documents d'autres personnes ou fichiers techniques.
"""

import re

# Fichiers personnels de Leblanc BAHIGA Mudarhi
# Chaque entrée : motif regex avec limite de mot \b
OWNER_PATTERNS = [
    re.compile(r'\bleblanc\b', re.IGNORECASE),
    re.compile(r'\bbahiga\b', re.IGNORECASE),
    re.compile(r'\bcv_?leblanc\b', re.IGNORECASE),
    re.compile(r'\bleblanc_?bahiga\b', re.IGNORECASE),
    re.compile(r'\bbahiga_?leblanc\b', re.IGNORECASE),
    re.compile(r'\bBahiga_Leblanc\b'),
    re.compile(r'\bcv_?bahiga\b', re.IGNORECASE),
]

# Références personnelles
PERSONAL_REF_PATTERNS = [
    re.compile(r'\battestation.*leblanc\b', re.IGNORECASE),
    re.compile(r'\bref_bahiga\b', re.IGNORECASE),
    re.compile(r'\blettre de motivation\b', re.IGNORECASE),
    re.compile(r'\bmotivation_\b', re.IGNORECASE),
    re.compile(r'\bcover letter\b', re.IGNORECASE),
]

# Fichiers EXCLUS (CV des autres, fichiers techniques, logs)
EXCLUDED_PATTERNS = [
    re.compile(r'\bjesse\b', re.IGNORECASE),
    re.compile(r'\bmuzalia\b', re.IGNORECASE),
    re.compile(r'\bgédéon\b', re.IGNORECASE),
    re.compile(r'\bgedeon\b', re.IGNORECASE),
    re.compile(r'\bomombo\b', re.IGNORECASE),
    re.compile(r'\bbanswetshibangu\b', re.IGNORECASE),
    re.compile(r'\bfofana\b', re.IGNORECASE),
    re.compile(r'\bséraphin\b', re.IGNORECASE),
    re.compile(r'\bseraphin\b', re.IGNORECASE),
    re.compile(r'\bantoine\b', re.IGNORECASE),
    re.compile(r'\bmugaruka\b', re.IGNORECASE),
    re.compile(r'\btoussaint\b', re.IGNORECASE),
    re.compile(r'\bjosaphat\b', re.IGNORECASE),
    re.compile(r'\bvalues-\b'),
    re.compile(r'\bmanifest-merger\b'),
    re.compile(r'\bmergeDebug\b'),
    re.compile(r'\boutput-metadata\b'),
    re.compile(r'\bsigning-config\b'),
    re.compile(r'\bstableIds\b'),
    re.compile(r'\bnavigation\.json\b'),
    re.compile(r'\bkapt_log\b'),
    re.compile(r'\bdeps\.txt\b'),
    re.compile(r'\bdeps_debug\b'),
    re.compile(r'\bquotation\b', re.IGNORECASE),
    re.compile(r'\b500kgh\b', re.IGNORECASE),
    re.compile(r'\bflow.?chart\b', re.IGNORECASE),
    re.compile(r'\bmaize.?mill\b', re.IGNORECASE),
    re.compile(r'\bcorn.?mill\b', re.IGNORECASE),
    re.compile(r'\bUganda Airlines\b'),
    re.compile(r'\bequity\b', re.IGNORECASE),
    re.compile(r'\bdai global\b', re.IGNORECASE),
    re.compile(r'\bimpact\b'),  # lettre de motivation Impact
    re.compile(r'\brti\b', re.IGNORECASE),
    re.compile(r'\bulb.cooperation\b', re.IGNORECASE),
    re.compile(r'\bulb-cooperation\b', re.IGNORECASE),
]


def is_owner_document(filename: str) -> bool:
    """Vérifie si un fichier appartient à Leblanc (vrai positif)."""
    # Exclure d'abord
    for pattern in EXCLUDED_PATTERNS:
        if pattern.search(filename):
            return False
    
    # Vérifier les profils personnels
    for pattern in OWNER_PATTERNS:
        if pattern.search(filename):
            return True
    
    # Vérifier les références
    for pattern in PERSONAL_REF_PATTERNS:
        if pattern.search(filename):
            return True
    
    return False


def get_boost_score(filename: str) -> float:
    """Retourne le multiplicateur de score pour un fichier."""
    if is_owner_document(filename):
        # Boost maximal pour les CV et lettres de motivation
        if re.search(r'\bcv\b', filename, re.IGNORECASE) or \
           re.search(r'\blettre de motivation\b', filename, re.IGNORECASE):
            return 2.5
        # Boost moyen pour les attestations et refs
        if re.search(r'\battestation\b', filename, re.IGNORECASE) or \
           re.search(r'\bref_\b', filename, re.IGNORECASE) or \
           re.search(r'\bmotivation\b', filename, re.IGNORECASE):
            return 2.0
        # Boost standard
        return 1.5
    return 1.0
