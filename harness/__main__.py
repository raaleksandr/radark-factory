"""Deprecated: `python -m harness ...` runs `python -m radark ...` (same stdout and exit code)."""
from __future__ import annotations

import sys

import radark.__main__ as _real

if __name__ == "__main__":
    print("note: `python -m harness` is deprecated, use `python -m radark` (kept for at least one release)",
          file=sys.stderr, flush=True)
    sys.exit(_real.main())
else:  # imported (e.g. `from harness.__main__ import main`): be the dispatcher module itself, start nothing
    sys.modules[__name__] = _real
