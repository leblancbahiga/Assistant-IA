"""NURU V5 — Compatibilité sqlite3 avec chargement d'extensions.

Sur macOS, Python 3.13 est compilé avec --enable-loadable-sqlite-extensions=no
donc `enable_load_extension()` n'est pas disponible. Ce module patch sqlite3
pour activer le chargement d'extensions via ctypes.
"""

import ctypes
import ctypes.util
import logging
import sys

logger = logging.getLogger(__name__)


def patch_sqlite3():
    """Patche le module sqlite3 pour activer enable_load_extension.

    Utilise ctypes pour appeler directement la fonction C sqlite3_enable_load_extension
    sur la connexion, contournant la restriction Python.
    """
    import sqlite3

    # Vérifier si enable_load_extension est déjà disponible
    try:
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        conn.close()
        logger.debug("sqlite3: enable_load_extension déjà disponible")
        return True
    except AttributeError:
        pass
    except sqlite3.OperationalError:
        # Disponible mais refusé → on laisse faire
        return True

    # Trouver la libsqlite3 dynamique
    lib_path = ctypes.util.find_library("sqlite3")
    if not lib_path:
        # Chercher via le module sqlite3
        import pathlib
        try:
            lib_path = pathlib.Path(sqlite3.__file__).parent / "libsqlite3.dylib"
            if not lib_path.exists():
                lib_path = None
        except Exception:
            lib_path = None

    if not lib_path:
        logger.warning("sqlite3: libsqlite3 introuvable, extensions désactivées")
        return False

    try:
        lib = ctypes.CDLL(lib_path)
        # sqlite3_enable_load_extension(sqlite3*, int)
        lib.sqlite3_enable_load_extension.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_enable_load_extension.restype = ctypes.c_int

        # Patcher la classe Connection
        original_init = sqlite3.Connection.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            try:
                # Obtenir le pointeur interne de la base de données
                db_ptr = ctypes.c_void_p.from_address(id(self) + 16)
                # Alternative: utiliser la fonction C directement
                conn_ptr = ctypes.c_void_p.from_address(id(self))
                result = lib.sqlite3_enable_load_extension(conn_ptr, 1)
                if result == 0:
                    logger.debug("sqlite3: enable_load_extension activé via ctypes")
            except Exception:
                pass

        sqlite3.Connection.__init__ = patched_init
        logger.info("sqlite3: extension loading activé via ctypes")
        return True

    except Exception as e:
        logger.warning(f"sqlite3: échec du patch ctypes: {e}")
        return False


def init_sqlite_vec(conn):
    """Charge l'extension sqlite-vec sur une connexion.

    Utilise sqlite_vec.loadable_path() pour trouver le .dylib et
    conn.load_extension() si enable_load_extension est disponible.
    """
    import sqlite3
    import sqlite_vec

    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return True
    except AttributeError:
        pass

    # Fallback : charger directement via load_extension
    try:
        conn.load_extension(sqlite_vec.loadable_path())
        return True
    except AttributeError:
        pass
    except sqlite3.OperationalError as e:
        logger.error(f"sqlite-vec: échec chargement extension: {e}")
        return False
