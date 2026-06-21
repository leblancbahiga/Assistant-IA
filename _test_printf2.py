"""Test what works with sandbox - part 2."""
import sys
sys.path.insert(0, 'src')
from src.tools.shell_exec import ShellSandbox
import tempfile, os
from pathlib import Path

sandbox = ShellSandbox()

with tempfile.TemporaryDirectory() as td:
    # Test heredoc
    test_path = str(Path(td) / 'test_heredoc.txt')
    cmd = "cat > " + test_path + " << 'EOF'\nABC\nEOF"
    r = sandbox.execute(cmd)
    print('heredoc success:', r.success, 'exit:', r.exit_code, 'stderr:', r.stderr)
    print('file exists:', os.path.exists(test_path))
    if os.path.exists(test_path):
        with open(test_path, 'rb') as f:
            print('content:', repr(f.read()))
    
    # Test simple echo
    test_path2 = str(Path(td) / 'test_echo.txt')
    r2 = sandbox.execute("echo 'ABC' > " + test_path2)
    print()
    print('echo success:', r2.success, 'exit:', r2.exit_code, 'stderr:', r2.stderr)
    print('file exists:', os.path.exists(test_path2))
    if os.path.exists(test_path2):
        with open(test_path2, 'rb') as f:
            print('content:', repr(f.read()))
    
    # Test printf with \\x
    test_path3 = str(Path(td) / 'test_printf.txt')
    # Use /usr/bin/printf explicitly
    r3 = sandbox.execute("/usr/bin/printf '\\x41\\x42\\x43' > " + test_path3)
    print()
    print('printf success:', r3.success, 'exit:', r3.exit_code, 'stderr:', r3.stderr)
    print('file exists:', os.path.exists(test_path3))
    if os.path.exists(test_path3):
        with open(test_path3, 'rb') as f:
            print('content:', repr(f.read()))

    # Test python3 writing
    test_path4 = str(Path(td) / 'test_py.txt')
    # Use python3 to write binary
    import subprocess
    subprocess.run("python3 -c \"open('" + test_path4 + "','wb').write(b'ABC')\"", shell=True)
    print()
    print('python3 subprocess file exists:', os.path.exists(test_path4))
    if os.path.exists(test_path4):
        with open(test_path4, 'rb') as f:
            print('content:', repr(f.read()))
