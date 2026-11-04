#!/usr/bin/env python3
"""Extract the public API packages from rbg.

The script intentionally copies declarative API files (types, constants, scheme
information, and generated DeepCopy methods) while excluding validation,
conversion, webhook, helper, and test logic. The generated client-go tree is
not copied.

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

API_FILE_NAMES = {
    "doc.go",
    "groupversion_info.go",
    "constant.go",
    "zz_generated.deepcopy.go",
}
API_FILE_SUFFIXES = ("_types.go",)

API_EXCLUDED_FILE_NAMES = {
    "helper.go",
    "register.go",
}
API_EXCLUDED_FILE_SUFFIXES = (
    "_test.go",
    "_validation.go",
    "_conversion.go",
    "_webhook.go",
    "_admission.go",
    "_default.go",
)
API_EXCLUDED_DIRECTORY_PREFIXES = ("pub/",)


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
        ["ls-tree", "-r", "--name-only", ref, "--", API_SOURCE],
    )
    paths = result.stdout.decode("utf-8").splitlines()
    return [path for path in paths if path and not path.endswith("/")]


def classify_api_file(relative: str) -> str:
    if relative.startswith("constants/"):
        name = relative.rsplit("/", 1)[-1]
        if name.endswith(".go") and not name.endswith("_test.go"):
            return "include"
        return "exclude"

    if relative.startswith(API_EXCLUDED_DIRECTORY_PREFIXES):
        return "exclude"

    match = re.fullmatch(r"v[0-9]+(?:alpha|beta)?[0-9]*/(.+)", relative)
    if match is None:
        return "unknown"

    name = match.group(1)
    if name in API_FILE_NAMES or name.endswith(API_FILE_SUFFIXES):
        return "include"
    if name in API_EXCLUDED_FILE_NAMES or name.endswith(API_EXCLUDED_FILE_SUFFIXES):
        return "exclude"
    return "unknown"


def extract_package_constants(content: bytes) -> bytes:
    """Extract top-level const blocks without helper functions.

    Some API types refer to default values that rbg declares in helper.go.
    Those values are public API variables/constants, while the rest of helper.go
    contains controller-oriented logic that should not be published here.
    """
    lines = content.decode("utf-8").splitlines(keepends=True)
    blocks: list[str] = []
    current_block: list[str] | None = None

    for line in lines:
        if current_block is None and line.strip() == "const (":
            current_block = [line]
            continue

        if current_block is not None:
            current_block.append(line)
            if line.strip() == ")":
                blocks.append("".join(current_block))
                current_block = None

    return "\n\n".join(blocks).encode("utf-8")


def remove_scheme_init_functions(content: str) -> str:
    """Remove package init functions that register types with SchemeBuilder."""
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    index = 0

    while index < len(lines):
        if lines[index].startswith("func init() {"):
            depth = 0
            while index < len(lines):
                depth += lines[index].count("{") - lines[index].count("}")
                index += 1
                if depth == 0:
                    break
            continue

        output.append(lines[index])
        index += 1

    return "".join(output)


def extract_registered_types(content: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"SchemeBuilder\.Register\(&(\w+)\{\}, &(\w+)\{\}\)"
    )
    return [(match.group(1), match.group(2)) for match in pattern.finditer(content)]


def parse_group_version(content: str) -> tuple[str, str]:
    match = re.search(
        r"GroupVersion\s*=\s*schema\.GroupVersion\{"
        r"\s*Group:\s*\"([^\"]+)\",\s*Version:\s*\"([^\"]+)\"",
        content,
    )
    if match is None:
        raise SyncError("could not parse GroupVersion from groupversion_info.go")
    return match.group(1), match.group(2)


def generate_groupversion_info(
    original_content: str,
    registered_types: list[tuple[str, str]],
) -> str:
    group, version = parse_group_version(original_content)
    prefix = original_content.split("import (", 1)[0]
    type_entries = "\n".join(
        f"        &{object_type}{{}},\n        &{object_list}{{}}," for object_type, object_list in registered_types
    )

    return (
        prefix
        + """import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

var (
	// GroupVersion is group version used to register these objects.
	GroupVersion = schema.GroupVersion{Group: """
        + f'"{group}", Version: "{version}"'
        + """}

	// SchemeGroupVersion is an alias of GroupVersion for compatibility.
	SchemeGroupVersion = GroupVersion

	// SchemeBuilder is used to add go types to the GroupVersionKind scheme.
	SchemeBuilder = runtime.NewSchemeBuilder(addKnownTypes)

	// AddToScheme adds the types in this group-version to the given scheme.
	AddToScheme = SchemeBuilder.AddToScheme
)

// addKnownTypes adds the list of known types to the given scheme.
func addKnownTypes(scheme *runtime.Scheme) error {
	scheme.AddKnownTypes(GroupVersion,
"""
        + type_entries
        + """
	)
	metav1.AddToGroupVersion(scheme, GroupVersion)
	return nil
}

// Resource takes an unqualified resource and returns a Group-qualified GroupResource.
func Resource(resource string) schema.GroupResource {
	return GroupVersion.WithResource(resource).GroupResource()
}
"""
    )


def rewrite_scheme_registration(root: Path) -> None:
    """Replace controller-runtime scheme registration with apimachinery."""
    for version_dir in sorted((root / "workloads").glob("v*")):
        if not version_dir.is_dir():
            continue

        groupversion_path = version_dir / "groupversion_info.go"
        if not groupversion_path.is_file():
            raise SyncError(f"missing groupversion_info.go in {version_dir}")

        registered_types: list[tuple[str, str]] = []
        for type_path in sorted(version_dir.glob("*_types.go")):
            content = type_path.read_text(encoding="utf-8")
            registered_types.extend(extract_registered_types(content))
            type_path.write_text(
                remove_scheme_init_functions(content), encoding="utf-8"
            )

        if not registered_types:
            raise SyncError(f"no registered API types found in {version_dir}")

        groupversion_content = groupversion_path.read_text(encoding="utf-8")
        groupversion_path.write_text(
            generate_groupversion_info(groupversion_content, registered_types),
            encoding="utf-8",
        )


def destination_path(destination_root: Path, source_path: str) -> Path:
    if source_path.startswith(API_SOURCE + "/"):
        relative = source_path[len(API_SOURCE) + 1 :]
        target = destination_root / "workloads" / relative
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
    ]
    if go_files:
        subprocess.run(
            ["gofmt", "-w", *(str(path) for path in go_files)],
            check=True,
        )


def validate_no_controller_runtime(root: Path) -> None:
    for path in sorted((root / "workloads").rglob("*.go")):
        if b"sigs.k8s.io/controller-runtime" in path.read_bytes():
            raise SyncError(f"controller-runtime import remains in {path}")


def copy_selected_files(
    source: Path,
    ref: str,
    destination_root: Path,
    files: list[str],
) -> tuple[int, int]:
    copied_api = 0

    for source_path in files:
        if source_path.startswith(API_SOURCE + "/"):
            relative = source_path[len(API_SOURCE) + 1 :]
            classification = classify_api_file(relative)
            if classification == "unknown":
                raise SyncError(f"unclassified API source file: {source_path}")
            if classification == "exclude":
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
        else:
            continue

        blob = run_git(source, ["show", f"{ref}:{source_path}"]).stdout
        target = destination_path(destination_root, source_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)

    return copied_api, 0


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

    clear_generated_tree(root, "workloads")
    clear_generated_tree(root, "client-go")
    copied_api, _ = copy_selected_files(source, args.ref, root, files)
    rewrite_scheme_registration(root)
    format_copied_go_files(root)
    validate_no_controller_runtime(root)

    if copied_api == 0:
        raise SyncError(f"selected no API files")

    if not args.skip_go_mod:
        subprocess.run(["go", "mod", "tidy"], cwd=root, check=True)

    if args.version:
        update_readme_version(root, args.version)

    print(
        f"Synced rbg {args.ref}: {copied_api} API files"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SyncError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
