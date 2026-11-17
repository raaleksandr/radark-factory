"""The example configuration files shipped as package data (ship-example-configs D1, D3).

`radark/examples/` has no `__init__.py`; the files are read through `importlib.resources` from the installed
`radark` package, never from a repository path. A zipped install is not a supported layout (as for the hooks)."""
from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

NAMES = {"radark": "radark.toml.example", "machine": "machine.toml.example"}


def path(kind: str) -> Path:
    """Absolute path of the packaged example file `kind` ("radark" or "machine")."""
    return Path(str(resources.files("radark") / "examples" / NAMES[kind])).resolve()


def read(kind: str) -> bytes:
    """The example file's bytes as stored."""
    return (resources.files("radark") / "examples" / NAMES[kind]).read_bytes()


def command(machine: bool, output: str | None, force: bool, show_path: bool) -> int:
    """`radark example-config`: print, write (-o, never overwriting without --force) or locate an example."""
    kind = "machine" if machine else "radark"
    if show_path and output is not None:
        print("example-config: --path cannot be combined with -o.", file=sys.stderr)
        return 2
    if force and output is None:
        print("example-config: --force needs -o FILE.", file=sys.stderr)
        return 2
    if show_path:
        print(path(kind))
        return 0
    data = read(kind)
    if output is None:
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return 0
    try:
        with open(output, "wb" if force else "xb") as fh:
            fh.write(data)
    except FileExistsError:
        print(f"{output} exists; not overwritten (add --force to replace it)", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"cannot write {output}: {e.strerror or e}", file=sys.stderr)
        return 2
    print(f"wrote {output} (from {NAMES[kind]})")
    return 0
