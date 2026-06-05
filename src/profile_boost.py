"""
NURU V6 — Profile Boost : booste les documents personnels de Leblanc.

Liste blanche des fichiers qui sont LES SIENS (CV, lettres de motivation, etc.).
Ces fichiers reçoivent un boost de score dans le RAG pour qu'ils apparaissent
en priorité par rapport aux documents d'autres personnes ou fichiers techniques.
"""

# Fichiers personnels de Leblanc BAHIGA Mudarhi
# Chaque entrée : motif de recherche (substring du nom de fichier)
OWNER_PROFILES = [
    # CV — toutes les versions
    "leblanc",
    "bahiga",
    "Leblanc",
    "BAHIGA",
    "bahiga_leblanc",
    "Bahiga_Leblanc",
    "CV_Leblanc",
    "cv_leblanc",
    "CV_Bahiga",
    "cv_bahiga",
    "CURRICULUM VITAE",  # Attention : peut match ceux des autres
]

# Fichiers IGNORÉS (même s'ils matchent un profil)
# On ne veut PAS les CV des autres personnes ni les fichiers techniques
EXCLUDED_FILES = [
    # CV d'autres personnes
    "jesse",
    "muzalia",
    "gédéon",
    "gedeon",
    "bak environnementaliste",
    "omombo",
    "banswetshibangu",
    "fofana",
    "séraphin",
    "seraphin",
    "antoine",
    "mugaruka",
    "toussaint",
    "josaphat",
    # Fichiers techniques / build
    "values-",
    "manifest-merger",
    "mergeDebug",
    "output-metadata",
    "signing-config",
    "stableIds",
    "navigation.json",
    "annotationProcessors",
    "file-map.txt",
    "requirements.txt",
    # Logs et dumps
    "kapt_log",
    "deps.txt",
    "deps_after",
    "deps_debug",
    # Autres documents non personnels
    "mots de passe",
    "500kgh",
    "5tpd maize",
    "10ton maize",
    "quotation",
    "quotation",
    "flow chart",
    "maize milling",
    "corn milling",
    "uganda airlines",
]

# Références personnelles (lettres de recommandation, attestations)
PERSONAL_REFERENCES = [
    "attestation de service rendu leblanc",
    "attestation de service rendu diobass",
    "ref_bahiga",
    "lettre de motivation",
    "motivation_",
    "cover letter",
]


def is_owner_document(filename: str) -> bool:
    """Vérifie si un fichier appartient à Leblanc (vrai positif)."""
    name_lower = filename.lower()
    
    # Exclure d'abord
    for excluded in EXCLUDED_FILES:
        if excluded.lower() in name_lower:
            return False
    
    # Vérifier les profils personnels
    for profile in OWNER_PROFILES:
        if profile.lower() in name_lower:
            return True
    
    # Vérifier les références
    for ref in PERSONAL_REFERENCES:
        if ref.lower() in name_lower:
            return True
    
    return False


def get_boost_score(filename: str) -> float:
    """Retourne le multiplicateur de score pour un fichier.

    Retourne 1.0 (pas de boost) ou plus (boosté).
    """
    if is_owner_document(filename):
        name_lower = filename.lower()
        # Boost maximal pour les CV et lettres de motivation
        if "cv" in name_lower or "lettre de motivation" in name_lower:
            return 2.5
        # Boost moyen pour les attestations et refs
        if "attestation" in name_lower or "ref_" in name_lower or "motivation" in name_lower:
            return 2.0
        # Boost standard
        return 1.5
    return 1.0
