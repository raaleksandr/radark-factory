"""Workflow profiles (workflow-profiles D2-D5): the work process of a team is a setting.

A profile names its phases, its wording, its prompt templates and its checks (did propose produce its artefact,
did a session make progress in the repository, is the artefact archived). Built-in profiles ship in
`radark/workflows/<name>/`; a profile directory next to the configuration may override single templates of a built-in
profile or define new profiles. Standard library only; this module imports nothing else of radark."""
from __future__ import annotations

import re
import string
import subprocess
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

BUILTINS = ("openspec", "plain")
DEFAULT_PROFILE = "openspec"
DEFAULT_DIR = "workflows"
PHASES = ("propose", "apply", "archive")  # the work phases a profile may declare; apply is required
TEMPLATES = ("propose", "apply", "apply-returned", "review", "archive", "act", "wrap-up-apply", "standing-rule")
# the `$name` variables a template may use (design D3); README "Template variables" lists exactly these
VARIABLES = ("handover", "title", "phase", "team", "expects", "change", "change_ref", "return_comment", "hub_sync",
             "closing", "apply_no_archive", "apply_local_todo", "blocked_note", "review_local_todo", "team_decides",
             "noun")
CLOSING_PHASES = ("propose", "apply", "review", "archive", "act")
PROFILE_KEYS = {"phases", "noun", "artefact_label", "finished_words", "based_on", "artifact_dir", "closing"}

CHANGE_LINE_RE = re.compile(r"^\s*CHANGE:\s*`?([A-Za-z0-9._-]+)`?\s*$", re.M)
CHECKED_RE = re.compile(r"^\s*[-*] \[[xX]\]", re.M)


class ProfileError(Exception):
    """A profile that cannot be used; config turns it into a ConfigError (exit 2)."""


# ---- git and file helpers (moved from __main__; behaviour unchanged)

def git_out(repo: Path, *args: str) -> str | None:
    """Read-only git query in a team repository; None when it is not a git repository or git fails."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def branch_heads(repo: Path) -> list[str] | None:
    out = git_out(repo, "for-each-ref", "--format=%(objectname)", "refs/heads")
    return None if out is None else sorted(set(out.split()))


def new_commits(repo: Path, old_heads: list[str]) -> bool:
    """A branch head points to a commit not reachable from the old heads (a reset or deletion is not progress)."""
    heads = branch_heads(repo)
    changed = [h for h in heads or [] if h not in old_heads]
    if not changed:
        return False
    out = git_out(repo, "rev-list", "--max-count=1", *changed, "--not", *old_heads, "--")
    return bool(out and out.strip())


def commits_outside(repo: Path, old_heads: list[str], prefix: str) -> bool:
    """The commits not reachable from the old heads change at least one path outside `prefix` (no-loop N2).
    If git cannot tell, they count (as before)."""
    changed = [h for h in branch_heads(repo) or [] if h not in old_heads]
    if not changed:
        return False
    out = git_out(repo, "-c", "core.quotepath=off", "log", "--name-only", "--format=", *changed,
                  "--not", *old_heads, "--")
    if out is None:
        return True
    return any(p.strip() and not p.strip().startswith(prefix) for p in out.splitlines())


def parse_change(text: str) -> str | None:
    found = CHANGE_LINE_RE.findall(text or "")
    return found[-1] if found else None


# ---- checks (design D5)

class PlainChecks:
    """No artefact: progress is new commits anywhere in the repository (plus hub activity, kept in the core)."""
    artifact_dir: str | None = None

    def artefact(self, repo: Path, handover: str, result_text: str, assistant_text: str) -> str | None:
        return None

    def archived(self, repo: Path, artefact: str | None) -> bool:
        return True

    def tasks(self, repo: Path, artefact: str | None) -> int | None:
        return None

    def snapshot(self, repo: Path, artefact: str | None) -> dict:
        """Taken when an item's work begins; `progress` compares against it (design T3)."""
        return {"heads": branch_heads(repo), "change": artefact, "tasks": self.tasks(repo, artefact)}

    def progress(self, repo: Path, base: dict, phase: str | None, ignored: list[str] | None = None) -> list[str]:
        """Repository progress sources since `base`: `commits`, `tasks`."""
        if base.get("heads") is not None and new_commits(repo, base["heads"]):
            return ["commits"]
        return []


class DirChecks(PlainChecks):
    """An artefact directory per item, `artifact_dir` with `{name}` in its last segment (`openspec/changes/{name}`
    for the `openspec` profile): propose produced it (a `CHANGE:` line or a directory citing the handover), archive
    removed it, apply commits count only outside it (no-loop N2), checked boxes in its `tasks.md` count."""

    def __init__(self, pattern: str):
        self.artifact_dir = pattern
        self.parent = pattern.rsplit("/", 1)[0] if "/" in pattern else ""
        self.last = pattern.rsplit("/", 1)[-1]

    def path(self, repo: Path, name: str) -> Path:
        return Path(repo) / self.artifact_dir.replace("{name}", name)

    def find(self, repo: Path, handover: str) -> str | None:
        """Fallback: newest artefact directory whose Markdown files mention the handover ID."""
        root = Path(repo) / self.parent if self.parent else Path(repo)
        if not root.is_dir():
            return None
        prefix, _, suffix = self.last.partition("{name}")
        found = []
        for d in root.iterdir():
            if not d.is_dir() or d.name == "archive" or not d.name.startswith(prefix) or not d.name.endswith(suffix):
                continue
            name = d.name[len(prefix):len(d.name) - len(suffix)]
            if not name:
                continue
            for f in d.rglob("*.md"):
                try:
                    if handover in f.read_text(encoding="utf-8", errors="replace"):
                        found.append((d.stat().st_mtime, name))
                        break
                except OSError:
                    continue
        return max(found)[1] if found else None

    def artefact(self, repo: Path, handover: str, result_text: str, assistant_text: str) -> str | None:
        return parse_change(result_text) or parse_change(assistant_text) or self.find(repo, handover)

    def archived(self, repo: Path, artefact: str | None) -> bool:
        return bool(artefact) and not self.path(repo, artefact).is_dir()

    def tasks(self, repo: Path, artefact: str | None) -> int | None:
        if not artefact:
            return None
        try:
            return len(CHECKED_RE.findall((self.path(repo, artefact) / "tasks.md").read_text(
                encoding="utf-8", errors="replace")))
        except OSError:
            return None

    def progress(self, repo: Path, base: dict, phase: str | None, ignored: list[str] | None = None) -> list[str]:
        sources = []
        if base.get("heads") is not None and new_commits(repo, base["heads"]):
            change = base.get("change")
            if (phase in ("apply", "act") and change
                    and not commits_outside(repo, base["heads"], self.artifact_dir.replace("{name}", change) + "/")):
                if ignored is not None:
                    ignored.append("change_notes")
            else:
                sources.append("commits")
        if base.get("change") and base.get("tasks") is not None:
            if (self.tasks(repo, base["change"]) or 0) > base["tasks"]:
                sources.append("tasks")
        return sources


# ---- profiles (design D2-D4)

@dataclass
class Profile:
    name: str
    phases: tuple[str, ...]
    noun: str
    artefact_label: str
    finished_words: str
    checks: PlainChecks
    templates: dict[str, string.Template] = field(default_factory=dict)
    closings: dict[str, string.Template] = field(default_factory=dict)
    sources: dict[str, str | None] = field(default_factory=dict)  # template -> override file, None = built-in
    builtin: bool = True

    @property
    def label(self) -> str:
        """How texts name a recorded artefact (`OpenSpec change`); empty when the profile records none."""
        return self.artefact_label if self.checks.artifact_dir else ""

    def has(self, phase: str) -> bool:
        return phase in self.phases

    def change_ref(self, change: str | None, handover: str) -> str:
        """How a prompt names the item's artefact (today's `_change_ref` for `openspec`)."""
        name = self.artefact_label or self.noun
        if not self.checks.artifact_dir:
            return f"the {self.noun} of {handover}"
        if change:
            return f"the {name} `{change}`"
        parent = self.checks.parent
        return f"the {name} in `{parent}/` that cites {handover} (find it first)"

    def render(self, template: str, values: dict[str, str]) -> str:
        if template not in self.templates:
            raise ProfileError(f"workflow profile '{self.name}' has no '{template}' prompt")
        return self.templates[template].substitute(values)

    def closing(self, phase: str, values: dict[str, str]) -> str:
        t = self.closings.get(phase)
        return t.substitute({**values, "closing": ""}) if t else ""

    def overrides(self) -> list[str]:
        return [f"{self.name}/{t}.md" for t, src in self.sources.items() if src and self.builtin]


def required_templates(phases) -> list[str]:
    need = ["apply", "apply-returned", "wrap-up-apply", "review", "act", "standing-rule"]
    need += [p for p in ("propose", "archive") if p in phases]
    return need


def _builtin_file(name: str, filename: str) -> str | None:
    f = resources.files("radark").joinpath("workflows", name, filename)
    try:
        return f.read_text(encoding="utf-8") if f.is_file() else None
    except OSError:
        return None


def _template(text: str, where: str, allow_closing: bool = True) -> string.Template:
    text = text.replace("\r\n", "\n")  # a checkout with CRLF line ends renders the same prompt
    if text.endswith("\n"):  # a file's single trailing newline is dropped (design D3)
        text = text[:-1]
    t = string.Template(text)
    if not t.is_valid():
        raise ProfileError(f"{where}: invalid `$` placeholder (write `$$` for a literal `$`)")
    allowed = set(VARIABLES) - (set() if allow_closing else {"closing"})
    unknown = [v for v in t.get_identifiers() if v not in allowed]
    if unknown:
        raise ProfileError(f"{where}: unknown template variable ${unknown[0]} "
                           f"(documented: {', '.join('$' + v for v in VARIABLES)})")
    return t


def _toml(text: str, where: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{where}: {exc}") from exc


def user_profiles(directory: Path | None) -> list[str]:
    """Names of the user-defined profiles in the profile directory (subdirectories with a `profile.toml`)."""
    if not directory or not directory.is_dir():
        return []
    return sorted(d.name for d in directory.iterdir()
                  if d.is_dir() and (d / "profile.toml").is_file() and d.name not in BUILTINS)


def _settings(name: str, data: dict, where: str, builtin: bool) -> dict:
    unknown = sorted(set(data) - PROFILE_KEYS)
    if unknown:
        raise ProfileError(f"{where}: unknown key '{unknown[0]}' (allowed: {', '.join(sorted(PROFILE_KEYS))})")
    phases = data.get("phases", ["apply"])
    if (not isinstance(phases, list) or not all(isinstance(p, str) for p in phases)
            or any(p not in PHASES for p in phases) or "apply" not in phases):
        raise ProfileError(f"{where}: phases must be a list of {', '.join(PHASES)} that includes apply, not {phases!r}")
    for key in ("noun", "artefact_label", "finished_words", "based_on", "artifact_dir"):
        if key in data and not isinstance(data[key], str):
            raise ProfileError(f"{where}: {key} must be a string")
    based_on = data.get("based_on")
    if based_on is not None and (builtin or based_on not in BUILTINS):
        raise ProfileError(f"{where}: based_on must name a built-in profile ({', '.join(BUILTINS)}), not {based_on!r}")
    pattern = data.get("artifact_dir")
    if pattern is not None:
        last = pattern.rsplit("/", 1)[-1]
        if pattern.count("{name}") != 1 or "{name}" not in last or pattern.startswith("/") or ".." in pattern:
            raise ProfileError(f"{where}: artifact_dir must be a repository-relative path with one {{name}} in its "
                               f"last segment, not {pattern!r}")
    elif any(p in phases for p in ("propose", "archive")):
        raise ProfileError(f"{where}: profile '{name}' declares a propose or archive phase but has no artifact_dir")
    closing = data.get("closing", {})
    if not isinstance(closing, dict) or any(k not in CLOSING_PHASES or not isinstance(v, str)
                                            for k, v in closing.items()):
        raise ProfileError(f"{where}: [closing] takes strings for {', '.join(CLOSING_PHASES)}")
    noun = data.get("noun", "task")
    return {"phases": tuple(p for p in PHASES if p in phases), "noun": noun,
            "artefact_label": data.get("artefact_label", noun),
            "finished_words": data.get("finished_words", "finished tasks"),
            "based_on": based_on, "artifact_dir": pattern, "closing": closing}


def _check_override_dir(d: Path, name: str) -> None:
    for f in d.iterdir():
        if f.name == "profile.toml" and name in BUILTINS:
            raise ProfileError(f"{f}: a directory named like the built-in profile '{name}' holds only prompt "
                               "overrides; a profile.toml there is not allowed (define a new profile under another "
                               "name)")
        if f.is_file() and f.suffix == ".md" and f.stem not in TEMPLATES:
            raise ProfileError(f"{f}: unknown prompt template '{f.stem}' (templates: {', '.join(TEMPLATES)})")


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Load and validate one profile: a built-in (with overrides from `directory/<name>/`) or a user-defined one."""
    own = directory / name if directory else None
    if own is not None and not own.is_dir():
        own = None
    if name in BUILTINS:
        where = f"built-in profile '{name}' (profile.toml)"
        settings = _settings(name, _toml(_builtin_file(name, "profile.toml") or "", where), where, True)
    elif own is not None and (own / "profile.toml").is_file():
        where = str(own / "profile.toml")
        settings = _settings(name, _toml((own / "profile.toml").read_text(encoding="utf-8"), where), where, False)
    else:
        found = user_profiles(directory)
        raise ProfileError(f"unknown workflow profile '{name}' (built-in: {', '.join(BUILTINS)}; "
                           + (f"found in {directory}: {', '.join(found)}" if found
                              else f"none found in {directory}" if directory else "no profile directory") + ")")
    if own is not None:
        _check_override_dir(own, name)
    base = settings["based_on"] or (name if name in BUILTINS else None)
    templates, sources = {}, {}
    for t in required_templates(settings["phases"]):
        path = own / f"{t}.md" if own is not None else None
        if path is not None and path.is_file():
            templates[t] = _template(path.read_text(encoding="utf-8"), str(path))
            sources[t] = str(path)
            continue
        text = _builtin_file(base, f"{t}.md") if base else None
        if text is None:
            raise ProfileError(f"workflow profile '{name}': missing prompt template "
                               f"{(own or Path(name)) / (t + '.md')}"
                               + (f" (not in the built-in profile '{base}' either)" if base else ""))
        templates[t] = _template(text, f"built-in profile '{base}': {t}.md")
        sources[t] = None
    closing_text = {}
    for fallback in ("plain", settings["based_on"]):
        if fallback and name not in BUILTINS:
            fb = _settings(fallback, _toml(_builtin_file(fallback, "profile.toml") or "", fallback), fallback, True)
            closing_text.update(fb["closing"])
    closing_text.update(settings["closing"])
    closings = {k: _template(v, f"workflow profile '{name}': [closing] {k}", allow_closing=False)
                for k, v in closing_text.items()}
    checks = DirChecks(settings["artifact_dir"]) if settings["artifact_dir"] else PlainChecks()
    return Profile(name=name, phases=settings["phases"], noun=settings["noun"],
                   artefact_label=settings["artefact_label"], finished_words=settings["finished_words"],
                   checks=checks, templates=templates, closings=closings, sources=sources,
                   builtin=name in BUILTINS)


_BUILTIN_CACHE: dict[str, Profile] = {}


def builtin(name: str = DEFAULT_PROFILE) -> Profile:
    """A built-in profile without overrides (the default of every prompt function)."""
    if name not in _BUILTIN_CACHE:
        _BUILTIN_CACHE[name] = load_profile(name, None)
    return _BUILTIN_CACHE[name]


def finished_words(profiles) -> str:
    """The goal check's finished work of the profiles in use, in order (design D8)."""
    return ", ".join(dict.fromkeys(["closed handovers", *(p.finished_words for p in profiles if p.finished_words)]))
