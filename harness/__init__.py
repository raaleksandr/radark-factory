"""Deprecated alias of the `radark` package, kept for at least one release.

`python -m harness ...` runs `python -m radark ...` (see `harness/__main__.py`). Importing `harness` or
`harness.<module>` gives the `radark` module objects: `harness.state is radark.state`."""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

import radark
from radark import *  # noqa: F401,F403  (the package exports nothing today; kept for future public names)

__doc__ = radark.__doc__ or __doc__
_PREFIX = __name__ + "."


class _Loader(importlib.abc.Loader):
    """Hands out the already-imported `radark.<sub>` module for `harness.<sub>`."""

    def __init__(self, target: str) -> None:
        self.target = target

    def create_module(self, spec):
        return importlib.import_module(self.target)

    def exec_module(self, module) -> None:
        pass  # the radark module is already executed


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Maps `harness.<sub>` (not `harness.__main__`, which must run the alias file) to `radark.<sub>`."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_PREFIX) or fullname == _PREFIX + "__main__":
            return None
        real = "radark." + fullname[len(_PREFIX):]
        if importlib.util.find_spec(real) is None:
            return None
        return importlib.util.spec_from_loader(fullname, _Loader(real))


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())
