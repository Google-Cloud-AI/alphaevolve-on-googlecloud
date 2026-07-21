# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""``ae skills install`` -- deliver the AlphaEvolve skills to a coding assistant.

Copies the six ``alpha_evolve_*`` skill directories from a source -- a local
checkout, or a GitHub repository fetched as a tarball -- into the skills
directory of a supported coding assistant. This replaces the standalone
``setup_ae.py`` installer. Its scope is skill delivery only (a pure file copy);
it does not install the CLI or any dependencies.
"""

from __future__ import annotations

from collections.abc import Callable
import http.client
import pathlib
import shutil
import sys
import tarfile
import tempfile
from typing import NoReturn, Optional
import urllib.parse
import urllib.request

import rich
import rich.markup
import typer

# The six skill directories this command delivers.
SKILL_DIRS: tuple[str, ...] = (
    "alpha_evolve_experiment_design",
    "alpha_evolve_runner",
    "alpha_evolve_monitor",
    "alpha_evolve_post_experiment",
    "alpha_evolve_orchestrator",
    "alpha_evolve_consultant",
)

# Canonical remote source, used when no local checkout is found and no
# ``--source`` is given. No per-CLI-version tags exist yet, so the ref defaults
# to ``main``; pin a specific commit with ``owner/repo@<sha>`` when needed.
_DEFAULT_REPO = "Google-Cloud-AI/alphaevolve-on-googlecloud"
_DEFAULT_REF = "main"

# Network timeout (seconds) for the tarball download.
_DOWNLOAD_TIMEOUT_S = 60

skills_app = typer.Typer(
    help="Manage AlphaEvolve skills.",
    no_args_is_help=True,
)


@skills_app.callback()
def _skills_group() -> None:
  """Manage AlphaEvolve skills.

  A no-op group callback: it keeps ``skills`` a command group so ``install``
  stays a named subcommand (a single-command Typer app would otherwise collapse,
  making ``ae skills install`` an unexpected-argument error).
  """


def _error(message: str) -> NoReturn:
  # Escape the message: it interpolates user-controlled paths/URLs that may
  # contain characters Rich would treat as markup.
  rich.print(
      f"[red]Error:[/red] {rich.markup.escape(message)}", file=sys.stderr
  )
  raise typer.Exit(1)


def _tool_destinations() -> tuple[tuple[str, pathlib.Path], ...]:
  """Return the (tool, default skills dir) menu; the first entry is the default."""
  home = pathlib.Path.home()
  return (
      ("Gemini CLI", home / ".gemini" / "config" / "skills"),
      ("Antigravity", home / ".gemini" / "config" / "skills"),
      ("Claude Code", home / ".claude" / "skills"),
      ("OpenAI Codex", home / ".agents" / "skills"),
  )


def _has_all_skills(directory: pathlib.Path) -> bool:
  return directory.is_dir() and all(
      (directory / name).is_dir() for name in SKILL_DIRS
  )


def _autodetect_local_source() -> pathlib.Path | None:
  """Search upward from the CWD for a checkout holding all six skill dirs.

  A tool's own installed skills directory is skipped, so running from inside
  (say) ``~/.claude/skills`` never picks that as the source -- which would make
  the source and destination the same and risk deleting the installed skills.

  Returns:
    The checkout's skills-root dir, or None if none was found.
  """
  tool_dirs = {path.resolve() for _, path in _tool_destinations()}
  cwd = pathlib.Path.cwd()
  for base in (cwd, *cwd.parents):
    for candidate in (base, base / "skills"):
      if _has_all_skills(candidate) and candidate.resolve() not in tool_dirs:
        return candidate
  return None


def _local_skills_root(path: pathlib.Path) -> pathlib.Path | None:
  """Return the dir under ``path`` holding skill dirs (``path`` or ``path/skills``)."""
  for candidate in (path, path / "skills"):
    if candidate.is_dir() and any(
        (candidate / name).is_dir() for name in SKILL_DIRS
    ):
      return candidate
  return None


def _parse_remote(source: str) -> tuple[str, str]:
  """Parse a remote source into ``(owner/repo, ref)``; ref defaults to ``main``."""
  spec = source[len("git+") :] if source.startswith("git+") else source
  if spec.startswith(("http://", "https://")):
    path = urllib.parse.urlparse(spec).path.strip("/")
    if path.endswith(".git"):
      path = path[: -len(".git")]
    parts = path.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
      _error(f"Cannot parse a GitHub owner/repo from {source!r}.")
    return f"{parts[0]}/{parts[1]}", _DEFAULT_REF
  # ``owner/repo[@ref]`` shorthand.
  repo_spec, _, maybe_ref = spec.partition("@")
  repo_spec = repo_spec.strip("/")
  if repo_spec.count("/") != 1:
    _error(f"Expected 'owner/repo[@ref]' or a GitHub URL, got {source!r}.")
  return repo_spec, (maybe_ref or _DEFAULT_REF)


def _fetch_tarball(url: str, dest: pathlib.Path) -> None:
  """Download ``url`` to ``dest`` (isolated so tests can stub the network out)."""
  try:
    request = urllib.request.Request(
        url, headers={"User-Agent": "AlphaEvolve CLI"}
    )
    with urllib.request.urlopen(
        request, timeout=_DOWNLOAD_TIMEOUT_S
    ) as response:
      with open(dest, "wb") as out:
        shutil.copyfileobj(response, out)
  except (OSError, ValueError, http.client.IncompleteRead) as e:
    # OSError covers URLError/TimeoutError, mid-stream connection resets, and
    # ENOSPC writing the temp file; IncompleteRead is a truncated response;
    # ValueError is a malformed URL (e.g. an unknown scheme).
    _error(f"Failed to download {url}: {e}")


def _is_skill_member(name: str) -> bool:
  """True for tar members under ``<top>/skills/alpha_evolve_*``."""
  parts = name.split("/")
  return (
      len(parts) >= 3
      and parts[1] == "skills"
      and parts[2].startswith("alpha_evolve_")
  )


def _extract_skills(tarball: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
  """Extract only the ``skills/alpha_evolve_*`` subtree; return its root dir."""
  try:
    with tarfile.open(tarball, "r:gz") as tar:
      members = [m for m in tar.getmembers() if _is_skill_member(m.name)]
      if not members:
        _error(
            "Downloaded archive contains no skills/alpha_evolve_* directories."
        )
      # filter="data" applies the stdlib path-traversal guard even though the
      # origin is trusted.
      tar.extractall(path=into, members=members, filter="data")
      # GitHub tarballs wrap all contents in a single top-level directory named
      # "<repo>-<ref>/", and _fetch_remote only ever fetches GitHub tarballs, so
      # taking the first path component to locate the skills root is safe.
      top = members[0].name.split("/", 1)[0]
  except tarfile.FilterError as e:
    # An unsafe member (e.g. path traversal) -- fail loudly and explicitly.
    _error(f"Refusing to extract an unsafe archive member: {e}")
  except tarfile.ReadError as e:
    _error(f"Downloaded archive is not a valid gzip tarball: {e}")
  except TypeError:
    # The tarfile extraction filter (the path-traversal guard) landed in
    # Python 3.11.4; older interpreters reject filter=. requires-python gates
    # this, but a from-source install can bypass it.
    _error("Extracting skills requires Python >= 3.11.4; please upgrade.")
  return into / top / "skills"


def _fetch_remote(
    owner_repo: str, ref: str
) -> tuple[pathlib.Path, Callable[[], None], str]:
  """Download and extract a GitHub repo tarball; return (skills_root, cleanup, desc)."""
  url = f"https://codeload.github.com/{owner_repo}/tar.gz/{ref}"
  tmp = pathlib.Path(tempfile.mkdtemp(prefix="ae_skills_"))

  def cleanup() -> None:
    shutil.rmtree(tmp, ignore_errors=True)

  try:
    tarball = tmp / "repo.tar.gz"
    _fetch_tarball(url, tarball)
    skills_root = _extract_skills(tarball, tmp)
  except BaseException:
    cleanup()
    raise
  return skills_root, cleanup, f"{owner_repo}@{ref} ({url})"


def _resolve_source(
    source: Optional[str],
) -> tuple[pathlib.Path, Optional[Callable[[], None]], str]:
  """Resolve ``--source`` to a skills-root dir plus an optional temp cleanup."""
  if source is None:
    local = _autodetect_local_source()
    if local is not None:
      return local, None, f"local checkout at {local}"
    rich.print(
        "[dim]No local checkout found; fetching from"
        f" {_DEFAULT_REPO}@{_DEFAULT_REF}.[/dim]"
    )
    return _fetch_remote(_DEFAULT_REPO, _DEFAULT_REF)

  candidate = pathlib.Path(source).expanduser()
  if candidate.exists():
    root = _local_skills_root(candidate)
    if root is None:
      _error(f"No AlphaEvolve skill directories found under {candidate}.")
    return root, None, f"local path {root}"

  owner_repo, ref = _parse_remote(source)
  return _fetch_remote(owner_repo, ref)


def _prompt_destination() -> pathlib.Path:
  """Present the tool menu and return the chosen skills directory."""
  destinations = _tool_destinations()
  rich.print("Select a destination for the AlphaEvolve skills:\n")
  for index, (name, path) in enumerate(destinations, start=1):
    rich.print(
        f"  {index}) {name}  ([dim]{rich.markup.escape(str(path))}[/dim])"
    )
  custom = len(destinations) + 1
  rich.print(f"  {custom}) Enter a custom path\n")

  choice = typer.prompt(f"Choice (1-{custom})", default="1").strip()
  if choice.isdigit():
    number = int(choice)
    if 1 <= number <= len(destinations):
      return destinations[number - 1][1]
    if number == custom:
      return pathlib.Path(
          typer.prompt("Enter the skills directory path")
      ).expanduser()
    _error(f"Invalid choice: {choice}.")
  # Non-numeric input is treated as a literal path.
  return pathlib.Path(choice).expanduser()


def _resolve_destination(
    tool: Optional[str], dest: Optional[pathlib.Path]
) -> pathlib.Path:
  if dest is not None:
    return dest.expanduser()
  if tool is not None:
    for name, path in _tool_destinations():
      if name.lower() == tool.lower():
        return path
    choices = ", ".join(name for name, _ in _tool_destinations())
    _error(f"Unknown tool {tool!r}. Choose from: {choices}.")
  return _prompt_destination()


def _same_dir(a: pathlib.Path, b: pathlib.Path) -> bool:
  return a.resolve() == b.resolve()


def _remove_path(path: pathlib.Path) -> None:
  """Remove ``path`` whether it is a symlink, a file, or a directory."""
  if path.is_symlink():
    path.unlink()  # Remove the link, never its target.
  elif path.is_dir():
    shutil.rmtree(path)
  elif path.exists():
    path.unlink()


def _copy_skills(
    skills_root: pathlib.Path, dest: pathlib.Path, force: bool
) -> None:
  """Install the skill dirs into ``dest``, staging then swapping into place.

  Staging every skill first makes the copy phase safe: a failure while copying
  leaves the destination untouched. The final swap is a per-directory rename
  (fast, but not all-or-nothing across the six), and each installed skill
  replaces the entire existing directory of that name.

  Args:
    skills_root: Directory containing the six skill dirs to install.
    dest: Destination skills directory.
    force: If True, replace existing skills without prompting.
  """
  if _same_dir(skills_root, dest):
    _error(
        f"Source and destination are the same directory ({dest}); the skills"
        " are already installed there."
    )

  existing = [name for name in SKILL_DIRS if (dest / name).exists()]
  if existing and not force:
    if not typer.confirm(
        f"{len(existing)} skill(s) already exist in {dest} and will be"
        " replaced. Continue?",
        default=True,
    ):
      rich.print("Aborted; nothing was changed.")
      raise typer.Exit(0)

  dest.mkdir(parents=True, exist_ok=True)
  # Stage on the destination's filesystem so the final swap is a fast rename.
  staging = pathlib.Path(
      tempfile.mkdtemp(prefix="ae_skills_stage_", dir=dest.parent)
  )
  try:
    for name in SKILL_DIRS:
      shutil.copytree(skills_root / name, staging / name)
    for name in SKILL_DIRS:
      target = dest / name
      _remove_path(target)  # Handles a stray file/symlink named like a skill.
      shutil.move(str(staging / name), str(target))
      rich.print(f"[green]Installed[/green] {name}")
  except OSError as e:
    _error(f"Failed to install skills into {dest}: {e}")
  finally:
    shutil.rmtree(staging, ignore_errors=True)


@skills_app.command("install")
def install(
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help=(
            "Local path (a dir with the alpha_evolve_* dirs, or a repo root"
            " with a skills/ subdir) OR a remote GitHub source"
            " (https://github.com/owner/repo, git+..., or owner/repo[@ref])."
            " Defaults to a local checkout, else the canonical GitHub repo."
        ),
    ),
    tool: Optional[str] = typer.Option(
        None,
        "--tool",
        help=(
            "Destination coding assistant (skips the menu): 'Gemini CLI',"
            " 'Antigravity', 'Claude Code', or 'OpenAI Codex'."
        ),
    ),
    dest: Optional[pathlib.Path] = typer.Option(
        None,
        "--dest",
        help="Explicit destination directory (overrides --tool).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing skills without prompting."
    ),
) -> None:
  """Install the AlphaEvolve skills into a coding assistant."""
  skills_root, cleanup, description = _resolve_source(source)
  try:
    rich.print(f"Source: [bold]{rich.markup.escape(description)}[/bold]")
    missing = [name for name in SKILL_DIRS if not (skills_root / name).is_dir()]
    if missing:
      _error(f"Source is missing skill directories: {', '.join(missing)}.")

    destination = _resolve_destination(tool, dest)
    _copy_skills(skills_root, destination, force)
    rich.print(
        f"\n[green]Done.[/green] Installed {len(SKILL_DIRS)} skills to"
        f" {rich.markup.escape(str(destination))}."
    )
  finally:
    if cleanup is not None:
      cleanup()
