#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Cross-platform installer for the AlphaEvolve CLI and skills.

Run this script from the extracted release zip directory using uv:

    uv run setup_ae.py

uv will automatically provide a Python >= 3.11 interpreter — no separate
Python installation is required.

The script will:
  1. Install the ae-cli wheel as a uv tool.
  2. Copy the AlphaEvolve skill directories to a location of your choice
     (supports Gemini CLI, Antigravity, Claude Code, and OpenAI Codex).
"""

from __future__ import annotations

from collections.abc import Sequence
import pathlib
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Supported coding tools and their default skill directories.  The first entry
# is used as the default when the user presses Enter without choosing.
_SKILLS_DESTINATIONS = (
    ("Gemini CLI", pathlib.Path.home() / ".gemini" / "config" / "skills"),
    ("Antigravity", pathlib.Path.home() / ".gemini" / "config" / "skills"),
    ("Claude Code", pathlib.Path.home() / ".claude" / "skills"),
    ("OpenAI Codex", pathlib.Path.home() / ".agents" / "skills"),
)

_SKILL_DIRS = (
    "alpha_evolve_experiment_design",
    "alpha_evolve_runner",
    "alpha_evolve_monitor",
    "alpha_evolve_post_experiment",
    "alpha_evolve_orchestrator",
    "alpha_evolve_consultant",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_header(text: str) -> None:
  width = 60
  print()
  print("=" * width)
  print(f"  {text}")
  print("=" * width)
  print()


def _print_step(n: int, text: str) -> None:
  print(f"  [{n}] {text}")


def _print_ok(text: str) -> None:
  print(f"  OK: {text}")


def _print_error(text: str) -> None:
  print(f"  ERROR: {text}", file=sys.stderr)


def _prompt(question: str, default: str = "") -> str:
  """Prompt the user for input with an optional default."""
  if default:
    answer = input(f"  {question} [{default}]: ").strip()
    return answer or default
  return input(f"  {question}: ").strip()


def _run(
    cmd: Sequence[str], check: bool = True
) -> subprocess.CompletedProcess[bytes]:
  """Run a command, printing it first.

  Args:
    cmd: Command and arguments to execute.
    check: If True, raise CalledProcessError on non-zero exit.

  Returns:
    The completed process result.
  """
  print(f"  > {' '.join(cmd)}")
  return subprocess.run(list(cmd), check=check)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _find_uv() -> str:
  """Locate the uv binary.

  When invoked via `uv run`, the UV environment variable points to the
  running uv binary.  Fall back to PATH lookup.

  Returns:
    Path to the uv binary.
  """
  from_env = shutil.which("uv")
  if from_env:
    return from_env
  _print_error(
      "Could not find uv. Please run this script with: uv run setup_ae.py"
  )
  sys.exit(1)


def _install_wheel(uv: str, script_dir: pathlib.Path) -> None:
  """Install the ae-cli wheel as a uv tool."""
  _print_step(1, "Installing ae-cli...")

  wheels = list(script_dir.glob("ae_cli-*.whl"))
  if not wheels:
    _print_error(
        f"No ae_cli-*.whl file found in {script_dir}. "
        "Make sure you are running this script from the extracted release zip."
    )
    sys.exit(1)

  wheel = wheels[0]
  print(f"  Using wheel: {wheel.name}")

  # --force ensures upgrades work even if a previous version is installed.
  # Exclude pre-release Python (e.g. 3.15 alpha) where transitive C-extension
  # dependencies like cffi may not yet ship binary wheels, causing source builds
  # that require a C compiler (that most users don't have).
  result = _run(
      [
          uv,
          "tool",
          "install",
          "ae-cli",
          "--from",
          str(wheel),
          "--force",
          "--python",
          ">=3.11,<3.15",
      ],
      check=False,
  )
  if result.returncode != 0:
    _print_error("Failed to install ae-cli. See output above.")
    sys.exit(1)

  _print_ok("ae-cli installed. Run 'ae --help' to verify.")


def _prompt_skills_path() -> pathlib.Path:
  """Present a menu of supported tools and return the chosen skills path."""
  print("  Select a destination for the AlphaEvolve skills:\n")
  for i, (tool, path) in enumerate(_SKILLS_DESTINATIONS, 1):
    rel = path.relative_to(pathlib.Path.home()).as_posix()
    print(f"    {i}) {tool:<16s} (~/{rel})")
  custom_index = len(_SKILLS_DESTINATIONS) + 1
  print(f"    {custom_index}) Enter a custom path")
  print()

  choice_str = _prompt(
      f"Choice (1-{custom_index})",
      default="1",
  )

  try:
    choice = int(choice_str)
  except ValueError:
    # Treat non-numeric input as a literal path for convenience.
    return pathlib.Path(choice_str).expanduser().resolve()

  if 1 <= choice <= len(_SKILLS_DESTINATIONS):
    return _SKILLS_DESTINATIONS[choice - 1][1]

  if choice == custom_index:
    custom = _prompt("Enter the skills directory path")
    return pathlib.Path(custom).expanduser().resolve()

  # Out-of-range number — fall back to default.
  print(f"  Invalid choice '{choice_str}', using default.")
  return _SKILLS_DESTINATIONS[0][1]


def _install_skills(script_dir: pathlib.Path) -> None:
  """Copy skill directories to the user's chosen location."""
  _print_step(2, "Installing AlphaEvolve skills...")

  # Check which skill directories are present in the release.
  available = [d for d in _SKILL_DIRS if (script_dir / d).is_dir()]
  if not available:
    print("  No skill directories found in the release — skipping.")
    return

  print(f"  Found {len(available)} skill(s): {', '.join(available)}")
  print()

  dest = _prompt_skills_path()

  print()
  for skill in available:
    src = script_dir / skill
    target = dest / skill
    if target.exists():
      print(f"  Updating {skill} (overwriting existing)...")
      shutil.rmtree(target)
    else:
      print(f"  Installing {skill}...")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, target)

  _print_ok(f"Skills installed to {dest}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
  """Run the AlphaEvolve CLI setup.

  Args:
    argv: Command-line arguments (unused). If unexpected arguments are present a
      warning is printed.
  """
  if argv and len(argv) > 1:
    print(f"  Warning: unexpected arguments: {argv[1:]}", file=sys.stderr)

  _print_header("AlphaEvolve CLI Setup")

  script_dir = pathlib.Path(__file__).resolve().parent

  uv = _find_uv()
  print()
  _install_wheel(uv, script_dir)
  print()
  _install_skills(script_dir)

  _print_header("Setup complete!")
  print("  Run 'ae --help' to get started.")
  print("  Run 'ae config' to configure your project and credentials.")
  print()


if __name__ == "__main__":
  main(sys.argv)
