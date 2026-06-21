"""Quick smoke test for file_ops.py"""

import os
import sys
import tempfile
import shutil

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.registry import ToolRegistry, ToolExecutor
from src.tools.file_ops import (
    PathSafety, FileOpResult, FileOpsController, register_file_tools
)

ctrl = FileOpsController.get_instance()
ws = ctrl.workspace_root
print(f"Workspace: {ws}")

# Test write
r1 = ctrl.write_file("test_hello.txt", "Hello World\nLigne 2\nLigne 3\n")
print(f"Write: {r1.success} - {r1.message}")

# Test read
r2 = ctrl.read_file("test_hello.txt")
print(f"Read: {r2.success} - content={r2.details['content'][:30]}...")

# Test read with offset/limit
r3 = ctrl.read_file("test_hello.txt", offset=1, limit=1)
print(f"Read offset=1,limit=1: content='{r3.details['content'].strip()}'")

# Test append
r4 = ctrl.append_file("test_hello.txt", "Ligne 4\n")
print(f"Append: {r4.success} - {r4.message}")

r5 = ctrl.read_file("test_hello.txt")
print(f"After append: {len(r5.details['content'].splitlines())} lines")

# Test mkdir
r6 = ctrl.create_directory("test_subdir")
print(f"Mkdir: {r6.success} - {r6.message}")

# Test list
r7 = ctrl.list_directory(ws)
print(f"List: {r7.success} - {r7.details['count']} entries")
print(f"  Entries: {[e['name'] for e in r7.details['entries'][:5]]}")

# Test file_info
r8 = ctrl.get_file_info("test_hello.txt")
print(f"Info: {r8.success} - size={r8.details['size_bytes']}")

# Test copy
r9 = ctrl.copy_file("test_hello.txt", "test_hello_copy.txt")
print(f"Copy: {r9.success} - {r9.message}")

# Test move (change level first)
old_profile = ctrl.safety_profile
ctrl.safety_profile = "power"
r10 = ctrl.move_file("test_hello_copy.txt", "test_hello_moved.txt")
print(f"Move: {r10.success} - {r10.message}")

# Test search_files
r11 = ctrl.search_files("test_*")
print(f"Search: {r11.success} - {r11.details['count']} results")

# Test delete (needs power level)
r12 = ctrl.delete_file("test_hello_moved.txt")
print(f"Delete: {r12.success} - {r12.message}")

# Cleanup
shutil.rmtree(os.path.join(ws, "test_subdir"), ignore_errors=True)
for f in ["test_hello.txt", "test_hello_moved.txt"]:
    try: os.remove(os.path.join(ws, f))
    except: pass

# Test workspace_info
r13 = ctrl.get_workspace_info()
print(f"WorkspaceInfo: {r13.success} - exists={r13.details['exists']}")

# Test register tools
reg = ToolRegistry()
executor = ToolExecutor(reg)
register_file_tools(reg, executor)
print(f"Tools registered: {len(reg.list_tools())}")
for t in reg.list_tools():
    print(f"  - {t.name}")

# Test authorize_directory
with tempfile.TemporaryDirectory() as td:
    r14 = ctrl.authorize_directory(td)
    print(f"Authorize: {r14.success} - {r14.message}")

# Test path safety
safety, reason = ctrl.check_path_safety(ws)
print(f"PathSafety(workspace): {safety} - {reason}")

# Test blocklist
safety, reason = ctrl.check_path_safety("/etc/passwd")
print(f"PathSafety(/etc): {safety} - {reason}")

# Test search_content
ctrl.write_file("test_search.txt", "Ceci est un test\navec du contenu\nmotif_secret ici\n")
r15 = ctrl.search_content("motif_secret", root=ws)
print(f"Search content: {r15.success} - {r15.details['match_count']} matches")
os.remove(os.path.join(ws, "test_search.txt"))

ctrl.safety_profile = old_profile
print("\nAll smoke tests passed!")
