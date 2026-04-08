from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SAFE_TOP_LEVEL_DIRS = {
    ".pytest_cache",
}

SAFE_TOP_LEVEL_FILES = {
    ".coverage",
}

PROTECTED_DIRS = {
    ".git",
    ".github",
    ".claude",
    "apps",
    "core",
    "data",
    "db",
    "departments",
    "docs",
    "policies",
    "scripts",
    "src",
    "storage",
    "tests",
}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_delete_dir(path: Path, root: Path, *, dry_run: bool) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not _is_relative_to(path, root):
        return False, "outside-root"
    if dry_run:
        return True, "dry-run"
    try:
        shutil.rmtree(path)
        return True, "removed"
    except PermissionError as exc:
        return False, f"locked: {exc}"
    except OSError as exc:
        return False, f"skipped: {exc}"


def _safe_delete_file(path: Path, root: Path, *, dry_run: bool) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not _is_relative_to(path, root):
        return False, "outside-root"
    if dry_run:
        return True, "dry-run"
    try:
        path.unlink()
        return True, "removed"
    except PermissionError as exc:
        return False, f"locked: {exc}"
    except OSError as exc:
        return False, f"skipped: {exc}"


def discover_targets(root: Path, *, include_deps: bool, include_logs: bool) -> tuple[list[Path], list[Path]]:
    dir_targets: list[Path] = []
    file_targets: list[Path] = []

    for name in SAFE_TOP_LEVEL_DIRS:
        candidate = root / name
        if candidate.exists():
            dir_targets.append(candidate)

    for name in SAFE_TOP_LEVEL_FILES:
        candidate = root / name
        if candidate.exists():
            file_targets.append(candidate)

    for cache_dir in root.rglob("__pycache__"):
        if cache_dir.is_dir() and ".git" not in cache_dir.parts:
            dir_targets.append(cache_dir)

    web_dist = root / "apps" / "web" / "dist"
    if web_dist.exists():
        dir_targets.append(web_dist)

    vite_cache = root / "apps" / "web" / "node_modules" / ".vite"
    if vite_cache.exists():
        dir_targets.append(vite_cache)

    if include_deps:
        node_modules = root / "apps" / "web" / "node_modules"
        if node_modules.exists():
            dir_targets.append(node_modules)

    if include_logs:
        logs_dir = root / "logs"
        if logs_dir.exists():
            dir_targets.append(logs_dir)
        for pid_file in root.glob(".*.pid"):
            file_targets.append(pid_file)

    # Deduplicate while preserving order.
    unique_dirs = list(dict.fromkeys(path for path in dir_targets if path.name not in PROTECTED_DIRS))
    unique_files = list(dict.fromkeys(file_targets))
    return unique_dirs, unique_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean generated artifacts for agentai-agency without touching source or runtime data."
    )
    parser.add_argument("--deps", action="store_true", help="Also remove apps/web/node_modules if it is not locked.")
    parser.add_argument("--logs", action="store_true", help="Also remove logs/ and PID files.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without deleting anything.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    dir_targets, file_targets = discover_targets(root, include_deps=args.deps, include_logs=args.logs)

    print("AgentAI cleanup")
    print(f"Root: {root}")
    print(f"Mode: {'dry-run' if args.dry_run else 'delete'}")
    print("")

    removed = 0
    skipped: list[str] = []

    for path in dir_targets:
        ok, detail = _safe_delete_dir(path, root, dry_run=args.dry_run)
        rel = path.relative_to(root)
        if ok:
            removed += 1
            print(f"[ok] {rel} ({detail})")
        elif detail != "missing":
            skipped.append(f"{rel} -> {detail}")
            print(f"[skip] {rel} ({detail})")

    for path in file_targets:
        ok, detail = _safe_delete_file(path, root, dry_run=args.dry_run)
        rel = path.relative_to(root)
        if ok:
            removed += 1
            print(f"[ok] {rel} ({detail})")
        elif detail != "missing":
            skipped.append(f"{rel} -> {detail}")
            print(f"[skip] {rel} ({detail})")

    print("")
    print(f"Removed targets: {removed}")
    if skipped:
        print("Skipped targets:")
        for item in skipped:
            print(f" - {item}")
        print("")
        print("Tip: close any dev server or editor process holding locked files, then run cleanup again.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
