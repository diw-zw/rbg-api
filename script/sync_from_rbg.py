#!/usr/bin/env python3
"""Extract the public API and generated client-go packages from rbg.

The script intentionally copies declarative API files (types, constants, scheme
information, and generated DeepCopy methods) while excluding validation,
conversion, webhook, helper, and test logic. The generated client-go tree is
copied in full because it is useful as a standalone client library.

Example:

    python3 script/sync_from_rbg.py \
        --source /path/to/rbg \
        --ref v0.8.0 \
        --version v0.8.0
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


API_SOURCE = "api/workloads"
CLIENT_SOURCE = "client-go"
TARGET_MODULE = "sigs.k8s.io/rbgs/api"
API_MODULE = "sigs.k8s.io/rbgs/api"
API_REPOSITORY = "github.com/sgl-project/rbg-api"
SOURCE_CLIENT_IMPORT = b"sigs.k8s.io/rbgs/client-go/"
TARGET_CLIENT_IMPORT = b"sigs.k8s.io/rbgs/api/client-go/"

API_FILE_NAMES = {
    "doc.go",
    "groupversion_info.go",
    "register.go",
    "constant.go",
    "zz_generated.deepcopy.go",
}
API_FILE_SUFFIXES = ("_types.go",)


class SyncError(RuntimeError):
    pass


def run_git(source: Path, args: Iterable[str]) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(source), *args]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SyncError(f"command failed ({' '.join(command)}): {detail}")
    return result


def ensure_repository(source: Path, ref: str) -> None:
    if not source.is_dir():
        raise SyncError(f"rbg source does not exist: {source}")
    if (source / ".git").exists() is False:
        raise SyncError(f"rbg source is not a Git repository: {source}")
    run_git(source, ["rev-parse", "--verify", f"{ref}^{{commit}}"])


def source_files(source: Path, ref: str) -> list[str]:
    result = run_git(
        source,
        ["ls-tree", "-r", "--name-only", ref, "--", API_SOURCE, CLIENT_SOURCE],
    )
    paths = result.stdout.decode("utf-8").splitlines()
    return [path for path in paths if path and not path.endswith("/")]


def include_api_file(relative: str) -> bool:
    if relative.startswith("constants/"):
        name = relative.rsplit("/", 1)[-1]
        return name.endswith(".go") and not name.endswith("_test.go")

    match = re.fullmatch(r"v[0-9]+(?:alpha|beta)?[0-9]*/(.+)", relative)
    if match is None:
        return False

    name = match.group(1)
    return (
        name in API_FILE_NAMES
        or (name.endswith(API_FILE_SUFFIXES) and not name.endswith("_test.go"))
    )


def rewrite_imports(content: bytes) -> bytes:
    return content.replace(SOURCE_CLIENT_IMPORT, TARGET_CLIENT_IMPORT)


def extract_package_constants(content: bytes) -> bytes:
    """Extract top-level const blocks without helper functions.

    Some API types refer to default values that rbg declares in helper.go.
    Those values are public API variables/constants, while the rest of helper.go
    contains controller-oriented logic that should not be published here.
    """
    pattern = re.compile(rb"(?m)^const\s*\([^)]*?^\)", re.DOTALL)
    return b"\n\n".join(match.group(0) for match in pattern.finditer(content))


def destination_path(destination_root: Path, source_path: str) -> Path:
    if source_path.startswith(API_SOURCE + "/"):
        relative = source_path[len(API_SOURCE) + 1 :]
        target = destination_root / "workloads" / relative
    elif source_path.startswith(CLIENT_SOURCE + "/"):
        relative = source_path[len(CLIENT_SOURCE) + 1 :]
        target = destination_root / "client-go" / relative
    else:
        raise SyncError(f"unexpected source path: {source_path}")

    resolved_root = destination_root.resolve()
    resolved_target = target.resolve()
    if resolved_root != resolved_target and resolved_root not in resolved_target.parents:
        raise SyncError(f"destination escapes repository: {target}")
    return target


def clear_generated_tree(root: Path, directory: str) -> None:
    target = root / directory
    if not target.exists():
        return
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_root not in resolved_target.parents:
        raise SyncError(f"refusing to remove directory outside repository: {target}")
    shutil.rmtree(target)


def format_copied_go_files(root: Path) -> None:
    go_files = [
        *sorted((root / "workloads").rglob("*.go")),
        *sorted((root / "client-go").rglob("*.go")),
    ]
    if go_files:
        subprocess.run(
            ["gofmt", "-w", *(str(path) for path in go_files)],
            check=True,
        )


def copy_selected_files(
    source: Path,
    ref: str,
    destination_root: Path,
    files: list[str],
) -> tuple[int, int]:
    copied_api = 0
    copied_client = 0

    for source_path in files:
        if source_path.startswith(API_SOURCE + "/"):
            relative = source_path[len(API_SOURCE) + 1 :]
            if not include_api_file(relative):
                if relative.endswith("/helper.go"):
                    blob = run_git(
                        source, ["show", f"{ref}:{source_path}"]
                    ).stdout
                    constants = extract_package_constants(blob)
                    if constants:
                        version_dir = relative.rsplit("/", 1)[0]
                        constant_path = (
                            destination_root
                            / "workloads"
                            / version_dir
                            / "helper_constants.go"
                        )
                        constant_path.write_text(
                            f"package {version_dir.split('/')[-1]}\n\n"
                            + constants.decode("utf-8")
                            + "\n",
                            encoding="utf-8",
                        )
                        copied_api += 1
                continue
            copied_api += 1
        elif source_path.startswith(CLIENT_SOURCE + "/"):
            if not source_path.endswith(".go"):
                continue
            copied_client += 1
        else:
            continue

        blob = run_git(source, ["show", f"{ref}:{source_path}"]).stdout
        target = destination_path(destination_root, source_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rewrite_imports(blob))

    return copied_api, copied_client


def update_go_directive(root: Path, source: Path, ref: str) -> None:
    go_mod = root / "go.mod"
    if not go_mod.is_file():
        return

    source_go_mod = run_git(source, ["show", f"{ref}:go.mod"]).stdout.decode("utf-8")
    match = re.search(r"^go\s+([0-9]+(?:\.[0-9]+)+)\s*$", source_go_mod, re.MULTILINE)
    if match is None:
        return

    current = go_mod.read_text(encoding="utf-8")
    updated, count = re.subn(r"^go\s+[^\n]+$", f"go {match.group(1)}", current, count=1)
    if count:
        go_mod.write_text(updated, encoding="utf-8")


def update_readme_version(root: Path, version: str) -> None:
    readme = root / "README.md"
    if not readme.is_file():
        return

    text = readme.read_text(encoding="utf-8")
    release_row = (
        f"| {version} | [{version}]"
        f"(https://github.com/sgl-project/rbg/releases/tag/{version})"
        " | v1alpha1, v1alpha2 | v1alpha2 |"
    )
    if release_row in text:
        return

    pattern = r"(## Release Compatibility\n\n\|[^\n]+\n\|[^\n]+\n)"
    replacement = rf"\1{release_row}\n"
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count:
        readme.write_text(updated, encoding="utf-8")


def update_version_references(root: Path, version: str) -> None:
    """Point repository usage examples at the release being synced."""
    examples_go_mod = root / "examples" / "go.mod"
    previous_version: str | None = None
    if examples_go_mod.is_file():
        text = examples_go_mod.read_text(encoding="utf-8")
        match = re.search(rf"^\s*{re.escape(API_MODULE)}\s+(v[^\s]+)", text, re.MULTILINE)
        previous_version = match.group(1) if match else None

        subprocess.run(
            [
                "go",
                "mod",
                "edit",
                f"-require={API_MODULE}@{version}",
                f"-replace={API_MODULE}={API_REPOSITORY}@{version}",
            ],
            cwd=examples_go_mod.parent,
            check=True,
        )

    if previous_version is None:
        return

    root_go_mod = root / "go.mod"
    if root_go_mod.is_file():
        text = root_go_mod.read_text(encoding="utf-8")
        root_go_mod.write_text(
            text.replace(previous_version, version), encoding="utf-8"
        )

    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        marker = "## Installation"
        if marker in text:
            before, after = text.split(marker, 1)
            after = after.replace(previous_version, version)
            readme.write_text(before + marker + after, encoding="utf-8")


def update_go_mod_versions(
    root: Path,
    source: Path,
    ref: str,
    run_go_mod: bool,
) -> None:
    source_go_mod = run_git(source, ["show", f"{ref}:go.mod"]).stdout.decode("utf-8")
    versions: dict[str, str] = {}
    for module in (
        "k8s.io/api",
        "k8s.io/apimachinery",
        "k8s.io/client-go",
        "sigs.k8s.io/controller-runtime",
    ):
        match = re.search(
            rf"^\s*{re.escape(module)}\s+(v[^\s\n]+)",
            source_go_mod,
            re.MULTILINE,
        )
        if match is None:
            raise SyncError(f"{module} not found in rbg {ref} go.mod")
        versions[module] = match.group(1)

    for module, version in versions.items():
        subprocess.run(
            ["go", "mod", "edit", f"-require={module}@{version}"],
            cwd=root,
            check=True,
        )

    if match_go := re.search(r"^go\s+([0-9]+(?:\.[0-9]+)+)\s*$", source_go_mod, re.MULTILINE):
        subprocess.run(
            ["go", "mod", "edit", f"-go={match_go.group(1)}"],
            cwd=root,
            check=True,
        )

    if run_go_mod:
        subprocess.run(["go", "mod", "tidy"], cwd=root, check=True)


def parse_args() -> argparse.Namespace:
    default_source = Path(__file__).resolve().parents[2] / "rbg"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=default_source,
        help=f"path to the rbg repository (default: {default_source})",
    )
    parser.add_argument("--ref", required=True, help="rbg Git tag, branch, or commit")
    parser.add_argument("--version", help="rbg-api release version, such as v0.8.0")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.cwd(),
        help="rbg-api repository root (default: current directory)",
    )
    parser.add_argument(
        "--skip-go-mod",
        action="store_true",
        help="copy files but do not update dependencies or run go mod tidy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    root = args.destination.expanduser().resolve()

    ensure_repository(source, args.ref)
    if not (root / "go.mod").is_file():
        raise SyncError(f"destination is not an rbg-api repository: {root}")

    files = source_files(source, args.ref)
    if not any(path.startswith(API_SOURCE + "/") for path in files):
        raise SyncError(f"no {API_SOURCE} files found in rbg {args.ref}")
    if not any(path.startswith(CLIENT_SOURCE + "/") for path in files):
        raise SyncError(f"no {CLIENT_SOURCE} files found in rbg {args.ref}")

    clear_generated_tree(root, "workloads")
    clear_generated_tree(root, "client-go")
    copied_api, copied_client = copy_selected_files(source, args.ref, root, files)
    format_copied_go_files(root)

    if copied_api == 0 or copied_client == 0:
        raise SyncError(
            f"selected no files (api={copied_api}, client-go={copied_client})"
        )

    if not args.skip_go_mod:
        update_go_directive(root, source, args.ref)
        update_go_mod_versions(root, source, args.ref, True)

    if args.version:
        update_readme_version(root, args.version)
        update_version_references(root, args.version)

    print(
        f"Synced rbg {args.ref}: {copied_api} API files, "
        f"{copied_client} client-go files"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SyncError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
