"""
Test unitaire du module RAMMonitor (version Asynchrone).
On injecte une fausse valeur de RAM basse pour forcer le déclenchement.
"""
import asyncio
import sys
import os
from unittest.mock import patch

# Ajouter le répertoire parent pour importer src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ram_monitor import RAMMonitor

# Variables de test partagées
test_callback_triggered = False
callback_force_level = None

async def async_callback(force=False):
    """Callback Asynchrone simulé.
    Dans la réalité: await llm_manager.unload_models()
    """
    global test_callback_triggered, callback_force_level
    await asyncio.sleep(0.1)  # Simule un travail asynchrone (libération VRAM, etc.)
    print(f"🔄 Callback ASYNC déclenché (force={force}) ! Libération...")
    test_callback_triggered = True
    callback_force_level = "force" if force else "warning"

def sync_callback(force=False):
    """Callback Synchrone simulé.
    Dans la réalité: gc.collect()
    """
    global test_callback_triggered, callback_force_level
    print(f"🔄 Callback SYNC déclenché (force={force}) ! Libération...")
    test_callback_triggered = True
    callback_force_level = "force" if force else "warning"

async def run_tests():
    global test_callback_triggered, callback_force_level
    
    print("🚀 Début du test RAMMonitor (Asynchrone)...")
    
    # Test 1 : Callback ASYNCHRONE en mode CRITIQUE (Moniteur ISOLÉ)
    print("\n--- TEST 1 : Callback ASYNC (Mode CRITIQUE) ---")
    test_callback_triggered = False
    callback_force_level = None
    monitor1 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor1.register_callback(async_callback)
    
    with patch.object(monitor1, 'get_available_ram_bytes', return_value=500 * 1024 * 1024):
        await monitor1.check_and_act()
    
    if test_callback_triggered and callback_force_level == "force":
        print("✅ TEST 1 RÉUSSI : Callback ASYNC déclenché en mode force.")
    else:
        print(f"❌ ÉCHEC TEST 1 : Triggers={test_callback_triggered}, Force={callback_force_level}")

    # Test 2 : Callback SYNCHRONE en mode WARNING (Moniteur ISOLÉ)
    print("\n--- TEST 2 : Callback SYNC (Mode WARNING) ---")
    test_callback_triggered = False
    callback_force_level = None
    monitor2 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor2.register_callback(sync_callback)
    
    with patch.object(monitor2, 'get_available_ram_bytes', return_value=1.5 * 1024 * 1024 * 1024):
        await monitor2.check_and_act()
    
    if test_callback_triggered and callback_force_level == "warning":
        print("✅ TEST 2 RÉUSSI : Callback SYNC déclenché en mode warning.")
    else:
        print(f"❌ ÉCHEC TEST 2 : Triggers={test_callback_triggered}, Force={callback_force_level}")

    # Test 3 : Mode OK (pas de déclenchement)
    print("\n--- TEST 3 : Mode OK (3 Go disponible) ---")
    test_callback_triggered = False
    callback_force_level = None
    monitor3 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor3.register_callback(async_callback)
    
    with patch.object(monitor3, 'get_available_ram_bytes', return_value=3.0 * 1024 * 1024 * 1024):
        await monitor3.check_and_act()
    
    if not test_callback_triggered:
        print("✅ TEST 3 RÉUSSI : Aucun déclenchement en mode OK.")
    else:
        print(f"❌ ÉCHEC TEST 3 : Callback déclenché à tort. Force={callback_force_level}")

    print("\n🏁 Fin des tests RAMMonitor.")

if __name__ == "__main__":
    asyncio.run(run_tests())