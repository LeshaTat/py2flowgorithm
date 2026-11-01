"""Install the flowgorithm library and the py2fprg converter for your Python, from this clone.

    python3 install.py              # install (again after moving the clone)
    python3 install.py --uninstall  # remove what it added

Afterwards every program run with this Python can `from flowgorithm import *`, and the commands
py2fprg, fprg-run, fprg-lint and fprg2svg work in any folder (as do `python3 -m py2fprg` and
`python3 -m fprg_run`). Nothing is copied: Python reads both projects from this clone, so a
`git pull` here updates them.

It adds two kinds of files:

* flowgorithm-repo.pth in this Python's user site-packages (in an active virtual environment: in
  its site-packages), naming library/src and converter/src of this clone. That is what
  `pip install --user -e` would add, and it also works where pip refuses user installs (Homebrew,
  Linux distributions).
* a small launcher script per command, in a folder on your PATH when there is one.
"""
from __future__ import annotations

import argparse
import os
import site
import subprocess
import sys
import sysconfig
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = [os.path.join(HERE, "library", "src"), os.path.join(HERE, "converter", "src")]
PTH = "flowgorithm-repo.pth"
COMMANDS = {"py2fprg": "py2fprg", "fprg-run": "fprg_run", "fprg-lint": "fprg_lint", "fprg2svg": "fprg2svg"}
MARK = "made by install.py of the flowgorithm repository"  # in every launcher, so only ours are removed


def in_virtualenv() -> bool:
    return sys.prefix != sys.base_prefix


def packages_folder() -> str:
    """Where this Python reads .pth files from: the user site-packages, or the virtual environment's."""
    if in_virtualenv():
        return sysconfig.get_paths()["purelib"]
    if not site.ENABLE_USER_SITE:
        sys.exit("this Python does not read a user site-packages folder (is PYTHONNOUSERSITE set?)")
    return site.getusersitepackages()


def on_path(folder: str) -> bool:
    wanted = os.path.normcase(os.path.abspath(folder))
    return any(os.path.normcase(os.path.abspath(p)) == wanted
               for p in os.environ.get("PATH", "").split(os.pathsep) if p)


def user_scripts() -> str:
    return sysconfig.get_path("scripts", sysconfig.get_preferred_scheme("user"))


def commands_folder(chosen: str | None) -> str:
    """Where the launchers go: --bin; the virtual environment's scripts; the user scripts folder,
    or ~/.local/bin when only that one is on PATH."""
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    if in_virtualenv():
        return sysconfig.get_paths()["scripts"]
    local = os.path.expanduser(os.path.join("~", ".local", "bin"))
    if os.name != "nt" and not on_path(user_scripts()) and on_path(local):
        return local
    return user_scripts()


def launcher_path(folder: str, name: str) -> str:
    return os.path.join(folder, name + ".cmd" if os.name == "nt" else name)


def launcher_text(module: str) -> str:
    if os.name == "nt":
        return f'@rem {MARK}\r\n@"{sys.executable}" -m {module} %*\r\n'
    return f'#!/bin/sh\n# {MARK}\nexec "{sys.executable}" -m {module} "$@"\n'


def ours(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return MARK in fh.read()
    except (OSError, UnicodeDecodeError):
        return False


def install(bin_folder: str) -> int:
    for source in SOURCES:
        if not os.path.isdir(source):
            sys.exit(f"{source} is missing: run install.py from a complete clone of the repository")
    folder = packages_folder()
    os.makedirs(folder, exist_ok=True)
    pth = os.path.join(folder, PTH)
    with open(pth, "w", encoding="utf-8") as fh:
        fh.write("\n".join(SOURCES) + "\n")
    print(f"library and converter: {pth}")

    os.makedirs(bin_folder, exist_ok=True)
    for name, module in COMMANDS.items():
        path = launcher_path(bin_folder, name)
        if os.path.exists(path) and not ours(path):
            print(f"  left {path} alone: it was not made by install.py")
            continue
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(launcher_text(module))
        os.chmod(path, 0o755)
    print(f"commands {', '.join(COMMANDS)}: {bin_folder}")

    # a fresh Python, away from this folder, must find both
    check = subprocess.run([sys.executable, "-c", "import flowgorithm, py2fprg; print(py2fprg.__version__)"],
                           cwd=tempfile.gettempdir(), capture_output=True, text=True)
    if check.returncode:
        print(f"the check failed:\n{check.stderr}", file=sys.stderr)
        return 1
    print(f"ok: the flowgorithm library and py2fprg {check.stdout.strip()} work with {sys.executable}")
    if in_virtualenv() and not on_path(bin_folder):
        print(f"\nThe commands work while the virtual environment is active ({sys.prefix}).")
    elif not on_path(bin_folder):
        print(f"\n{bin_folder} is not on your PATH, so type `{os.path.basename(sys.executable)} -m py2fprg` "
              "for now, or add the folder to PATH:")
        if os.name == "nt":
            print("  Settings > System > About > Advanced system settings > Environment Variables > Path")
        else:
            print(f"  echo 'export PATH=\"{bin_folder}:$PATH\"' >> ~/.zprofile    (bash: ~/.bash_profile)")
    print("\nAnother Python (a different version, IDLE, an IDE) needs its own run of install.py.")
    return 0


def uninstall(bin_folder: str | None) -> int:
    removed = []
    pth = os.path.join(packages_folder(), PTH)
    if os.path.exists(pth):
        os.remove(pth)
        removed.append(pth)
    folders = [bin_folder] if bin_folder else []
    folders += [commands_folder(None), user_scripts(), os.path.expanduser(os.path.join("~", ".local", "bin"))]
    for folder in dict.fromkeys(os.path.abspath(f) for f in folders):
        for name in COMMANDS:
            path = launcher_path(folder, name)
            if os.path.exists(path) and ours(path):
                os.remove(path)
                removed.append(path)
    print("removed:\n  " + "\n  ".join(removed) if removed else "nothing to remove")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Install the flowgorithm library and the py2fprg converter "
                                            "for this Python, straight from this clone.")
    p.add_argument("--uninstall", action="store_true", help="remove what install.py added")
    p.add_argument("--bin", help="the folder for the commands (default: one on your PATH when possible)")
    a = p.parse_args(argv)
    return uninstall(a.bin) if a.uninstall else install(commands_folder(a.bin))


if __name__ == "__main__":
    sys.exit(main())
