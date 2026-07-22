"""NURU Kernel — package du noyau central.

Remplace les imports directs entre modules par un registre central.
Tout service est accessible via kernel.get('name').

Migration progressive :
  Phase 3.0 : Créer le Kernel aux côtés de l'architecture existante
  Phase 3.1 : Migrer les modules un par un vers kernel.get()
  Phase 3.2 : Supprimer les imports directs
"""

from src.kernel.registry import ServiceRegistry
from src.kernel.kernel import NuruKernel

__all__ = ["ServiceRegistry", "NuruKernel"]
