"""Test what works with sandbox."""
import sys
sys.path.insert(0, 'src')
from src.tools.shell_exec import ShellSandbox
import tempfile, os
from pathlib import Path

sandbox = ShellSandbox()

with tempfile.TemporaryDirectory() as td:
    test_path = str(Path(td) / 'test.txt')
    
    # Method 1: echo -n
    r = sandbox.execute("echo -n ABC > " + test_path)
    print('echo -n success:', r.success, 'exit:', r.exit_code, 'stderr:', r.stderr)
    print('file exists:', os.path.exists(test_path))
    if os.path.exists(test_path):
        with open(test_path, 'rb') as f:
            print('content:', repr(f.read()))
    
    # Method 2: printf via /bin/bash
    test_path2 = str(Path(td) / 'test2.txt')
    r2 = sandbox.execute("/bin/bash -c 'printf \"\\x41\\x42\\x43\" > " + test_path2 + "'")
    print()
    print('bash printf success:', r2.success, 'exit:', r2.exit_code, 'stderr:', r2.stderr)
    print('file exists:', os.path.exists(test_path2))
    if os.path.exists(test_path2):
        with open(test_path2, 'rb') as f:
            print('content:', repr(f.read()))
    
    # Method 3: bash $'...'
    test_path3 = str(Path(td) / 'test3.txt')
    r3 = sandbox.execute("echo -n $'\\x41\\x42\\x43' > " + test_path3)
    print()
    print('bash $ hex success:', r3.success, 'exit:', r3.exit_code, 'stderr:', r3.stderr)
    print('file exists:', os.path.exists(test_path3))
    if os.path.exists(test_path3):
        with open(test_path3, 'rb') as f:
            print('content:', repr(f.read()))
