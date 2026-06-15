#!/usr/bin/env python3
"""Cut, build, verify, and publish a multiomics_explorer release.

Mirrors the KG repo's `/release-kg` process spine — five phases:
preflight -> CHANGELOG cut (pauses for polish) -> commit/tag/push ->
uv build + wheel verification -> publish GitHub Release.

See `.claude/skills/release-explorer/SKILL.md` for usage and
`references/PHASES.md` for phase-by-phase mechanics.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Repo root: .claude/skills/release-explorer/release_explorer.py
# parents[0]=release-explorer, [1]=skills, [2]=.claude, [3]=repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
DIST_DIR = REPO_ROOT / "dist"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?$")
TAG_PREFIX = "v"

# Files Phase 3 stages + commits. On --resume these are expected to be dirty
# (the Phase-2 cut left them so); preflight tolerates them without --allow-dirty.
RESUME_OWNED_PATHS = {"CHANGELOG.md", "pyproject.toml"}


# --------------------------------------------------------------------------- helpers


def log(msg: str, level: str = "info") -> None:
    prefix = {
        "info": "[*]",
        "ok": "[ok]",
        "warn": "[!]",
        "err": "[x]",
        "dry": "[dry-run]",
    }[level]
    print(f"{prefix} {msg}")


def fail(msg: str) -> None:
    log(msg, "err")
    sys.exit(1)


def run(cmd, *, capture: bool = False, check: bool = True, dry: bool = False, cwd: Path | None = None) -> str:
    """Run a command. Honors dry-run by logging only."""
    pretty = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    if dry:
        log(f"would run: {pretty}", "dry")
        return ""
    result = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        check=check,
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    return result.stdout.strip() if capture else ""


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        fail("Could not find a `version = \"...\"` line in pyproject.toml")
    return m.group(1)


def semver_to_pep440(version: str) -> str:
    """Mirror uv build's PEP 440 normalization.

    0.1.0-alpha.1 -> 0.1.0a1
    0.1.0-beta.2  -> 0.1.0b2
    0.1.0-rc.1    -> 0.1.0rc1
    0.1.0         -> 0.1.0
    """
    return (
        version.replace("-alpha.", "a")
        .replace("-beta.", "b")
        .replace("-rc.", "rc")
    )


# --------------------------------------------------------------------------- phase 1


def phase_1_preflight(args, ctx: dict) -> None:
    log("Phase 1: Preflight")

    # Version regex
    if not VERSION_RE.match(args.version):
        fail(f"Version {args.version!r} does not match {VERSION_RE.pattern}")
    log(f"version regex ok: {args.version}", "ok")

    # pyproject.toml version must match arg
    pyproject_version = read_pyproject_version()
    if pyproject_version != args.version:
        fail(
            f"pyproject.toml version is {pyproject_version!r}, arg is {args.version!r}.\n"
            f"  Bump pyproject.toml first, or invoke with the correct version arg."
        )
    log(f"pyproject.toml version matches: {pyproject_version}", "ok")

    # Tools on PATH
    for tool in ("git", "uv", "gh"):
        if shutil.which(tool) is None:
            fail(f"Required tool not on PATH: {tool}")
    log("tools: git, uv, gh on PATH", "ok")

    # gh auth — skip under --dry-run (we don't make network calls there)
    if args.dry_run:
        log("gh auth check skipped (--dry-run)", "dry")
    else:
        run(["gh", "auth", "status"], capture=True)
        log("gh auth ok", "ok")

    # Git state
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True, cwd=REPO_ROOT)
    sha = run(["git", "rev-parse", "HEAD"], capture=True, cwd=REPO_ROOT)
    sha_short = run(["git", "rev-parse", "--short", "HEAD"], capture=True, cwd=REPO_ROOT)
    porcelain = run(["git", "status", "--porcelain"], capture=True, cwd=REPO_ROOT)
    dirty = bool(porcelain.strip())

    if dirty and not args.allow_dirty:
        # On --resume, the Phase-2 CHANGELOG cut (and any prose the operator
        # polished during the pause) is intentionally left uncommitted —
        # Phase 3 stages + commits exactly these files. Tolerate them being
        # dirty without forcing --allow-dirty; any *other* stray change still
        # aborts so accidental edits don't ride along into the release commit.
        dirty_paths = {
            line[3:].strip() for line in porcelain.splitlines() if line.strip()
        }
        unexpected = dirty_paths - RESUME_OWNED_PATHS if args.resume else dirty_paths
        if unexpected:
            hint = "Commit, stash, or use --allow-dirty."
            if args.resume and dirty_paths & RESUME_OWNED_PATHS:
                hint = (
                    "On --resume only CHANGELOG.md / pyproject.toml may be dirty "
                    "(Phase 3 commits them); the rest must be clean.\n"
                    f"  Unexpected: {', '.join(sorted(unexpected))}\n"
                    "  Commit, stash, or use --allow-dirty."
                )
            fail(f"Working tree dirty:\n{porcelain}\n{hint}")
        log("resume: only CHANGELOG/pyproject dirty (Phase 3 commits them)", "ok")

    # In-sync-with-origin check (real runs only)
    if not args.dry_run:
        run(["git", "fetch", "origin", branch], check=False, cwd=REPO_ROOT, capture=True)
        behind = run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
            capture=True, check=False, cwd=REPO_ROOT,
        )
        if behind and int(behind) > 0 and not args.allow_dirty:
            fail(f"Local branch is {behind} commits behind origin/{branch}. Pull first.")

    log(f"git: branch={branch}, sha={sha_short}, dirty={dirty}", "ok")

    # Unit tests — skip under --dry-run; mandatory otherwise
    if args.dry_run:
        log("unit tests skipped (--dry-run)", "dry")
    else:
        log("running pytest tests/unit/ ...", "info")
        run(["uv", "run", "pytest", "tests/unit/", "-q"], cwd=REPO_ROOT)
        log("unit tests green", "ok")

    ctx.update(
        {
            "branch": branch,
            "git_sha": sha,
            "git_sha_short": sha_short,
            "git_dirty": dirty,
            "version": args.version,
            "tag": f"{TAG_PREFIX}{args.version}",
            "pep440_version": semver_to_pep440(args.version),
        }
    )


# --------------------------------------------------------------------------- phase 2


def phase_2_changelog_cut(args, ctx: dict) -> None:
    log("Phase 2: CHANGELOG cut")

    if not CHANGELOG.exists():
        fail(f"{CHANGELOG} not found. Bootstrap it (Keep-a-Changelog format) first.")

    text = CHANGELOG.read_text()
    version_marker = f"## [{args.version}]"

    if version_marker in text:
        log(f"CHANGELOG already has section for {args.version} — skipping cut", "ok")
        return

    unreleased_re = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
    m = unreleased_re.search(text)
    if not m:
        fail(f"{CHANGELOG} has no `## [Unreleased]` section. Add one (empty is fine).")

    body_start = m.end()
    next_section = re.search(r"^## \[", text[body_start:], re.MULTILINE)
    body_end = body_start + (next_section.start() if next_section else len(text) - body_start)
    body = text[body_start:body_end].rstrip()

    # If the captured body is empty (no bullets at all), insert a placeholder so
    # the new version section isn't a bare heading.
    has_content = bool(re.search(r"^\s*-", body, re.MULTILINE))
    if not has_content:
        body = "\n\n_No entries — placeholder._\n"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_unreleased = "## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n\n"
    new_version_section = f"## [{args.version}] - {today}{body}\n\n"

    new_text = text[: m.start()] + new_unreleased + new_version_section + text[body_end:].lstrip("\n")
    new_text = new_text.rstrip() + "\n"

    if args.dry_run:
        log(f"would cut [Unreleased] -> [{args.version}] - {today}", "dry")
        return

    CHANGELOG.write_text(new_text)
    log(f"cut [Unreleased] -> [{args.version}] - {today}", "ok")

    if not args.resume:
        print()
        print("=" * 60)
        print(f"PAUSE: CHANGELOG cut done.")
        print("=" * 60)
        print(f"Review and polish {CHANGELOG.relative_to(REPO_ROOT)} as needed,")
        print(f"then re-run with --resume to continue.")
        sys.exit(0)


# --------------------------------------------------------------------------- phase 3


def phase_3_commit_tag_push(args, ctx: dict) -> None:
    log("Phase 3: Commit + tag + push")

    tag = ctx["tag"]
    commit_subject = f"chore(release): {tag}"

    # Commit (skip if HEAD subject already matches)
    last_subject = run(["git", "log", "-1", "--pretty=%s"], capture=True, cwd=REPO_ROOT)
    if last_subject == commit_subject:
        log(f"commit {commit_subject!r} already at HEAD — skipping", "ok")
    elif args.dry_run:
        log(f"would commit: {commit_subject}", "dry")
    else:
        # Stage release-relevant files (CHANGELOG always; pyproject in case it
        # was just-in-time bumped). Use check=False so missing/clean files don't
        # error.
        run(["git", "add", "CHANGELOG.md"], cwd=REPO_ROOT, check=False)
        run(["git", "add", "pyproject.toml"], cwd=REPO_ROOT, check=False)
        staged = run(["git", "diff", "--cached", "--name-only"], capture=True, cwd=REPO_ROOT)
        if staged:
            run(["git", "commit", "-m", commit_subject], cwd=REPO_ROOT)
            log(f"committed: {commit_subject}", "ok")
        else:
            log("nothing staged — skipping commit", "ok")

    # Tag (skip if exists locally)
    existing_tags = run(["git", "tag", "-l", tag], capture=True, cwd=REPO_ROOT)
    if existing_tags.strip():
        log(f"tag {tag} already exists — skipping", "ok")
    elif args.dry_run:
        log(f"would tag: {tag}", "dry")
    else:
        run(
            ["git", "tag", "-a", tag, "-m", f"Explorer release {ctx['version']}"],
            cwd=REPO_ROOT,
        )
        log(f"tagged: {tag}", "ok")

    # Push
    if args.dry_run:
        log(f"would push: git push origin {ctx['branch']} --follow-tags", "dry")
    else:
        run(["git", "push", "origin", ctx["branch"], "--follow-tags"], cwd=REPO_ROOT)
        log("pushed branch + tag to origin", "ok")


# --------------------------------------------------------------------------- phase 4


def phase_4_build_verify(args, ctx: dict) -> None:
    log("Phase 4: Build + verify")

    # Clean dist/
    if DIST_DIR.exists():
        if args.dry_run:
            log(f"would remove existing {DIST_DIR.relative_to(REPO_ROOT)}/", "dry")
        else:
            shutil.rmtree(DIST_DIR)

    # Build
    if args.dry_run:
        log("would run: uv build", "dry")
        ctx["wheel"] = f"multiomics_explorer-{ctx['pep440_version']}-py3-none-any.whl"
        ctx["sdist"] = f"multiomics_explorer-{ctx['pep440_version']}.tar.gz"
        log(f"would verify wheel + sdist + venv install", "dry")
        return

    run(["uv", "build"], cwd=REPO_ROOT)
    log("uv build ok", "ok")

    # Locate artifacts
    wheels = list(DIST_DIR.glob("*.whl"))
    sdists = list(DIST_DIR.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        fail(
            f"Expected exactly one wheel + one sdist in {DIST_DIR}; "
            f"got {len(wheels)} wheel(s), {len(sdists)} sdist(s)."
        )
    wheel_path = wheels[0]
    sdist_path = sdists[0]
    ctx["wheel"] = wheel_path.name
    ctx["sdist"] = sdist_path.name
    log(f"artifacts: {ctx['wheel']}, {ctx['sdist']}", "ok")

    # Wheel filename must carry the expected PEP 440 version (catches the
    # rare case where pyproject and the wheel disagree)
    expected_in_name = ctx["pep440_version"]
    if expected_in_name not in wheel_path.name:
        fail(
            f"Wheel filename {wheel_path.name!r} does not contain expected "
            f"PEP 440 version {expected_in_name!r}."
        )

    # Wheel content: no leakage; LICENSE present
    forbidden_prefixes = (
        "multiomics_explorer/inputs/",
        "multiomics_explorer/cli/",
        "tests/",
    )
    forbidden_names = (".env", ".venv/")

    with zipfile.ZipFile(wheel_path) as z:
        names = z.namelist()

    leaks = [
        n for n in names
        if any(n.startswith(p) for p in forbidden_prefixes)
        or any(bad in n for bad in forbidden_names)
    ]
    if leaks:
        fail("Wheel contains forbidden paths:\n  " + "\n  ".join(leaks[:10]))
    log("wheel: no inputs/cli/tests/env leakage", "ok")

    if not any("LICENSE" in n for n in names):
        fail("Wheel does not contain LICENSE")
    log("wheel: LICENSE present", "ok")

    # Throwaway venv install + import + console-script check
    venv_dir = Path(f"/tmp/explorer-release-check-{ctx['version']}")
    if venv_dir.exists():
        shutil.rmtree(venv_dir)

    run(["uv", "venv", str(venv_dir)], capture=True)
    run(
        ["uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), str(wheel_path)],
        capture=True,
    )
    py = str(venv_dir / "bin" / "python")
    run([py, "-c", "import multiomics_explorer"], capture=True)
    log("wheel: imports cleanly in throwaway venv", "ok")

    mcp_bin = venv_dir / "bin" / "multiomics-kg-mcp"
    if not mcp_bin.exists():
        fail(f"Console script not installed: {mcp_bin}")
    log("wheel: multiomics-kg-mcp console script present", "ok")

    shutil.rmtree(venv_dir)


# --------------------------------------------------------------------------- phase 5


def phase_5_publish(args, ctx: dict) -> None:
    log("Phase 5: Publish")

    # metadata.json
    metadata = {
        "version": ctx["version"],
        "tag": ctx["tag"],
        "git_sha": ctx["git_sha"],
        "git_sha_short": ctx["git_sha_short"],
        "git_branch": ctx["branch"],
        "git_dirty": ctx["git_dirty"],
        "python_requires": ">=3.11",
        "wheel": ctx["wheel"],
        "sdist": ctx["sdist"],
        "stamped_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = DIST_DIR / "metadata.json"

    if args.dry_run:
        log(f"would write {metadata_path.relative_to(REPO_ROOT)} with:", "dry")
        print(json.dumps(metadata, indent=2))
    else:
        DIST_DIR.mkdir(exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        log(f"wrote {metadata_path.relative_to(REPO_ROOT)}", "ok")

    # Extract CHANGELOG section
    text = CHANGELOG.read_text() if CHANGELOG.exists() else ""
    section_re = re.compile(
        rf"^## \[{re.escape(ctx['version'])}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = section_re.search(text)
    if m:
        notes = m.group(1).strip() + "\n"
    else:
        log(f"[{ctx['version']}] section not found in CHANGELOG — using minimal notes", "warn")
        notes = f"Release {ctx['version']}.\n"

    notes_fragment = REPO_ROOT / f".release-notes-{ctx['version']}.md"

    if args.dry_run:
        log(f"would write {notes_fragment.name} (preview):", "dry")
        print("---")
        print(notes[:600] + ("\n... [truncated]" if len(notes) > 600 else ""))
        print("---")
    else:
        notes_fragment.write_text(notes)
        log(f"wrote {notes_fragment.name}", "ok")

    # gh release create
    is_prerelease = "-" in ctx["version"]
    gh_args = [
        "gh", "release", "create", ctx["tag"],
        "--title", f"Explorer {ctx['version']}",
        "--notes-file", str(notes_fragment),
    ]
    if is_prerelease:
        gh_args.append("--prerelease")
    if args.draft:
        gh_args.append("--draft")

    wheel_path = DIST_DIR / ctx["wheel"]
    sdist_path = DIST_DIR / ctx["sdist"]
    gh_args.extend([str(wheel_path), str(sdist_path), str(metadata_path)])

    if args.dry_run:
        log(f"would run: {' '.join(gh_args)}", "dry")
    else:
        run(gh_args)
        log(f"GitHub Release created: {ctx['tag']}", "ok")
        # cleanup
        if notes_fragment.exists():
            notes_fragment.unlink()

    # Final announcement
    print()
    print("=" * 60)
    print(f"  Released: {ctx['tag']}")
    print("=" * 60)
    print(f"  Tag:      {ctx['tag']}")
    print(f"  Wheel:    dist/{ctx['wheel']}")
    print(f"  Sdist:    dist/{ctx['sdist']}")
    print(f"  Release:  https://github.com/wosnat/multiomics_explorer/releases/tag/{ctx['tag']}")
    print()
    print(f"  Install:  uv add git+https://github.com/wosnat/multiomics_explorer.git@{ctx['tag']}")
    print()
    print("  Cross-repo coordination reminder:")
    print(f"    The KG declares a min-compatible explorer via Schema_info.mcp_min_version.")
    print(f"    Confirm the paired KG release accepts {ctx['version']} (KG plan §2.3).")


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cut, build, verify, and publish a multiomics_explorer release.",
    )
    parser.add_argument(
        "version",
        help="X.Y.Z[-(alpha|beta|rc).N] (without the 'v' prefix). "
             "Must match pyproject.toml's `version` field.",
    )
    parser.add_argument("--draft", action="store_true", help="Publish GitHub Release as a draft.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Exercise every phase, mutate nothing (no commits, tags, push, build, gh).")
    parser.add_argument("--resume", action="store_true",
                        help="Skip the post-CHANGELOG-cut pause.")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Skip working-tree-clean and behind-origin checks.")
    args = parser.parse_args()

    if args.dry_run:
        log("DRY RUN — no mutations will be made", "dry")
        print()

    ctx: dict = {}
    phase_1_preflight(args, ctx)
    phase_2_changelog_cut(args, ctx)
    phase_3_commit_tag_push(args, ctx)
    phase_4_build_verify(args, ctx)
    phase_5_publish(args, ctx)

    print()
    log("Done.", "ok")


if __name__ == "__main__":
    main()
