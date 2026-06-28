"""
Test unitaire du module RAMMonitor (version Asynchrone).
On injecte une fausse valeur de RAM basse pour forcer le déclenchement.
"""
import asyncio
import sys
import os
from unittest.mock import patch
import pytest

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
    test_callback_triggered = True
    callback_force_level = "force" if force else "warning"

def sync_callback(force=False):
    """Callback Synchrone simulé.
    Dans la réalité: gc.collect()
    """
    global test_callback_triggered, callback_force_level
    test_callback_triggered = True
    callback_force_level = "force" if force else "warning"

@pytest.mark.asyncio
async def test_ram_monitor_async_critical():
    global test_callback_triggered, callback_force_level
    
    # Test 1 : Callback ASYNCHRONE en mode CRITIQUE (Moniteur ISOLÉ)
    test_callback_triggered = False
    callback_force_level = None
    monitor1 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor1.register_callback(async_callback)
    
    with patch.object(monitor1, 'get_available_ram_bytes', return_value=500 * 1024 * 1024):
        await monitor1.check_and_act()
    
    assert test_callback_triggered, "Le callback asynchrone doit être déclenché"
    assert callback_force_level == "force", "Le niveau de force doit être 'force' en cas de RAM critique"

@pytest.mark.asyncio
async def test_ram_monitor_sync_warning():
    global test_callback_triggered, callback_force_level
    
    # Test 2 : Callback SYNCHRONE en mode WARNING (Moniteur ISOLÉ)
    test_callback_triggered = False
    callback_force_level = None
    monitor2 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor2.register_callback(sync_callback)
    
    with patch.object(monitor2, 'get_available_ram_bytes', return_value=int(1.5 * 1024 * 1024 * 1024)):
        await monitor2.check_and_act()
    
    assert test_callback_triggered, "Le callback synchrone doit être déclenché"
    assert callback_force_level == "warning", "Le niveau de force doit être 'warning' en cas de RAM warning"

@pytest.mark.asyncio
async def test_ram_monitor_ok():
    global test_callback_triggered, callback_force_level
    
    # Test 3 : Mode OK (pas de déclenchement)
    test_callback_triggered = False
    callback_force_level = None
    monitor3 = RAMMonitor(warning_threshold_gb=2.0, critical_threshold_gb=1.0)
    monitor3.register_callback(async_callback)
    
    with patch.object(monitor3, 'get_available_ram_bytes', return_value=int(3.0 * 1024 * 1024 * 1024)):
        await monitor3.check_and_act()
    
    assert not test_callback_triggered, "Le callback ne doit pas être déclenché si la RAM disponible est suffisante"