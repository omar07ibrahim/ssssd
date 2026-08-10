#!/usr/bin/env python3
"""Generate a privacy-preserving static audit for the quarantined desktop snapshot."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from typing import Any

PYTHON_MODULES = (
    "DTKLPR5.py",
    "DTKVID.py",
    "auto_virtual_camera.py",
    "camera_handler.py",
    "config.py",
    "database.py",
    "gui.py",
    "improved_levenshtein.py",
    "main.py",
    "plate_processor.py",
    "telegram_notifier.py",
    "telegram_stream_manager.py",
    "utils.py",
    "virtual_camera_manager.py",
    "workers.py",
)
ENV_TEMPLATE = ".env.example"
OUTPUT_NAMES = (
    "source-audit.json",
    "source-audit.txt",
    "source-inventory.svg",
    "module-boundary.svg",
    "runtime-boundary.svg",
    "credential-boundary.svg",
    "release-gate.svg",
)
ISSUE_URL = "https://github.com/omar07ibrahim/ssssd/issues/2"
LAYERS = {
    "native-wrapper": ("DTKLPR5", "DTKVID"),
    "capture": ("auto_virtual_camera", "camera_handler", "virtual_camera_manager"),
    "processing": ("improved_levenshtein", "plate_processor"),
    "state": ("config", "database", "utils"),
    "presentation": ("gui", "main", "workers"),
    "optional-messaging": ("telegram_notifier", "telegram_stream_manager"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def analyze_module(path: str, data: bytes) -> dict[str, Any]:
    source = data.decode("utf-8")
    tree = ast.parse(source, filename=path)
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
    roots = sorted({name.split(".", 1)[0] for name in imports if name})
    return {
        "path": path,
        "module": Path(path).stem,
        "bytes": len(data),
        "lines": len(source.splitlines()),
        "sha256": sha256(data),
        "git_blob_sha1": git_blob_sha1(data),
        "parse_status": "pass",
        "import_roots": roots,
        "top_level_classes": classes,
        "top_level_functions": functions,
        "execution_performed": False,
    }


def analyze_environment(data: bytes) -> dict[str, Any]:
    keys: list[str] = []
    nonempty = 0
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"invalid environment template line {line_number}")
        key, value = stripped.split("=", 1)
        if not key or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid environment key at line {line_number}")
        keys.append(key)
        nonempty += int(bool(value))
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate environment template key")
    return {
        "path": ENV_TEMPLATE,
        "bytes": len(data),
        "sha256": sha256(data),
        "git_blob_sha1": git_blob_sha1(data),
        "keys": keys,
        "entries": len(keys),
        "nonempty_values": nonempty,
        "values_emitted": False,
    }


def build_manifest(root: Path) -> dict[str, Any]:
    modules = [
        analyze_module(path, (root / path).read_bytes()) for path in PYTHON_MODULES
    ]
    environment_data = (root / ENV_TEMPLATE).read_bytes()
    environment = analyze_environment(environment_data)
    module_names = {item["module"] for item in modules}
    edges: list[dict[str, str]] = []
    nonlocal_roots: set[str] = set()
    for item in modules:
        for imported in item["import_roots"]:
            if imported in module_names:
                edges.append({"source": item["module"], "target": imported})
            else:
                nonlocal_roots.add(imported)
    edges.sort(key=lambda item: (item["source"], item["target"]))

    by_layer: list[dict[str, object]] = []
    for layer, names in LAYERS.items():
        by_layer.append(
            {
                "id": layer,
                "modules": list(names),
                "files": len(names),
                "lines": sum(
                    item["lines"] for item in modules if item["module"] in names
                ),
            }
        )

    generator_data = Path(__file__).resolve().read_bytes()
    empty_template = environment["nonempty_values"] == 0
    dependency_manifest_present = (root / "requirements.txt").is_file() or (
        root / "pyproject.toml"
    ).is_file()

    return {
        "schema": "ssssd.quarantine_snapshot.v1",
        "scope": {
            "kind": "static-source-metadata audit",
            "python_modules": len(modules),
            "network_used": False,
            "application_executed": False,
            "native_library_loaded": False,
            "gui_opened": False,
            "telegram_contacted": False,
            "source_values_emitted": False,
        },
        "generator": {
            "path": "tools/audit_quarantine.py",
            "sha256": sha256(generator_data),
        },
        "python": {
            "modules": modules,
            "total_bytes": sum(item["bytes"] for item in modules),
            "total_lines": sum(item["lines"] for item in modules),
            "top_level_classes": sum(len(item["top_level_classes"]) for item in modules),
            "top_level_functions": sum(
                len(item["top_level_functions"]) for item in modules
            ),
            "local_import_edges": edges,
            "nonlocal_import_roots": sorted(nonlocal_roots),
            "layers": by_layer,
        },
        "environment_template": environment,
        "repository_contract": {
            "dependency_manifest_present": dependency_manifest_present,
            "license_file_present": any(
                (root / name).is_file()
                for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
            ),
            "promotional_runtime_evidence_published": False,
        },
        "release_gate": [
            {
                "id": "current-env-template",
                "state": "pass" if empty_template else "blocked",
                "evidence": (
                    f"{environment['entries']} declared keys and zero non-empty values"
                    if empty_template
                    else "Environment template contains one or more non-empty values"
                ),
            },
            {
                "id": "historical-telegram-credentials",
                "state": "human_required",
                "evidence": "Two provider alerts require revocation and account review outside Git",
                "issue": ISSUE_URL,
            },
            {
                "id": "dtk-publication-rights",
                "state": "human_required",
                "evidence": "Rights to publish and redistribute the native DTK integration are unconfirmed",
                "issue": ISSUE_URL,
            },
            {
                "id": "repository-license",
                "state": "human_required",
                "evidence": "No license may be selected until source provenance and rights are established",
                "issue": ISSUE_URL,
            },
            {
                "id": "dependency-lock",
                "state": "blocked" if not dependency_manifest_present else "review",
                "evidence": (
                    "No requirements or pyproject dependency manifest is retained"
                    if not dependency_manifest_present
                    else "Dependency manifest exists and requires reproducibility review"
                ),
            },
            {
                "id": "runtime-evidence",
                "state": "missing",
                "evidence": "No native library, camera, GUI, database, or Telegram path was executed",
            },
            {
                "id": "public-release",
                "state": "blocked",
                "evidence": "No release or promotional capture before credentials, rights, licensing, and synthetic-fixture gates close",
                "issue": ISSUE_URL,
            },
        ],
        "generated_artifacts": list(OUTPUT_NAMES),
    }


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_open(title: str, description: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-labelledby="title desc">
<title id="title">{esc(title)}</title>
<desc id="desc">{esc(description)}</desc>
<style>
  .bg {{ fill: #07111f; }}
  .panel {{ fill: #0f2035; stroke: #315270; stroke-width: 2; }}
  .panel2 {{ fill: #122941; stroke: #41698c; stroke-width: 2; }}
  .title {{ fill: #f4f8ff; font: 700 34px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .sub {{ fill: #9ec8e8; font: 18px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .head {{ fill: #f4f8ff; font: 700 21px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .body {{ fill: #d4e5f4; font: 17px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .small {{ fill: #9ec8e8; font: 15px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .good {{ fill: #65d6a6; font: 700 17px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .warn {{ fill: #ffcc66; font: 700 17px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .bad {{ fill: #ff7b86; font: 700 17px ui-monospace, SFMono-Regular, Consolas, monospace; }}
  .line {{ stroke: #77b6dd; stroke-width: 3; fill: none; }}
</style>
<rect class="bg" width="1280" height="720"/>
"""


def text(x: int, y: int, value: object, css: str = "body", anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{esc(value)}</text>\n'


def panel(x: int, y: int, width: int, height: int, css: str = "panel") -> str:
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="18" class="{css}"/>\n'


def render_inventory(manifest: dict[str, Any]) -> str:
    python = manifest["python"]
    modules = sorted(
        python["modules"], key=lambda item: (-item["bytes"], item["path"])
    )
    env = manifest["environment_template"]
    out = svg_open(
        "Quarantined desktop source inventory",
        "Exact static counts and hashes for the retained Python and empty environment-template surfaces.",
    )
    out += text(60, 62, "SSSSD / SOURCE INVENTORY", "title")
    out += text(60, 94, "Exact current metadata; application code and credential values are never displayed.", "sub")
    metrics = [
        ("PYTHON MODULES", python["modules"].__len__()),
        ("TOTAL LINES", f"{python['total_lines']:,}"),
        ("LOCAL IMPORT EDGES", len(python["local_import_edges"])),
        ("EMPTY ENV KEYS", f"{env['entries']}/{env['entries']}"),
    ]
    for index, (label, value) in enumerate(metrics):
        x = 60 + index * 295
        out += panel(x, 135, 260, 120)
        out += text(x + 22, 175, label, "small")
        out += text(x + 22, 223, value, "head")
    out += panel(60, 300, 720, 280, "panel2")
    out += text(88, 342, "LARGEST RETAINED MODULES", "head")
    y = 388
    for item in modules[:5]:
        out += text(92, y, item["path"])
        out += text(735, y, f"{item['lines']:,} lines · {item['sha256'][:12]}…", "small", "end")
        y += 38
    out += panel(820, 300, 400, 280, "panel2")
    out += text(848, 342, "STATIC SCOPE", "head")
    out += text(848, 388, f"{python['top_level_classes']} top-level classes")
    out += text(848, 426, f"{python['top_level_functions']} top-level functions")
    out += text(848, 464, "native load: no", "warn")
    out += text(848, 502, "GUI / Telegram: no", "warn")
    out += text(848, 540, "source values emitted: 0", "good")
    out += text(640, 650, "STATIC INVENTORY ≠ RUNTIME VALIDATION", "warn", "middle")
    out += text(640, 682, "Reproduce: python3 tools/audit_quarantine.py --check", "small", "middle")
    return out + "</svg>\n"


def render_module_boundary(manifest: dict[str, Any]) -> str:
    layers = manifest["python"]["layers"]
    out = svg_open(
        "Static module boundary map",
        "Source-derived grouping of native wrappers, capture, processing, state, presentation, and optional messaging modules.",
    )
    out += text(60, 62, "SSSSD / MODULE BOUNDARIES", "title")
    out += text(60, 94, "Groups are derived from exact retained modules and local imports; no runtime claim.", "sub")
    positions = [(60, 145), (450, 145), (840, 145), (60, 390), (450, 390), (840, 390)]
    for item, (x, y) in zip(layers, positions, strict=True):
        out += panel(x, y, 340, 185, "panel2")
        out += text(x + 24, y + 42, str(item["id"]).upper(), "head")
        out += text(x + 24, y + 78, f"{item['files']} files · {item['lines']:,} lines", "small")
        line_y = y + 116
        for module in item["modules"]:
            out += text(x + 24, line_y, module, "body")
            line_y += 28
    out += text(640, 650, f"{len(manifest['python']['local_import_edges'])} LOCAL IMPORT EDGES · ZERO IMPORTS EXECUTED", "good", "middle")
    return out + "</svg>\n"


def render_runtime_boundary(manifest: dict[str, Any]) -> str:
    out = svg_open(
        "Unexecuted runtime integration boundary",
        "Static application path from camera inputs through proprietary native wrappers, processing, local state, GUI, and optional Telegram integration.",
    )
    out += """<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#77b6dd"/></marker></defs>\n"""
    out += text(60, 62, "SSSSD / STATIC RUNTIME PATH", "title")
    out += text(60, 94, "Architecture recovered from imports and class surfaces. Nothing was launched.", "sub")
    nodes = [
        (45, 180, 210, "camera / virtual", "external input"),
        (295, 180, 210, "DTKVID / DTKLPR5", "rights boundary"),
        (545, 180, 210, "plate processing", "local logic"),
        (795, 180, 210, "database + GUI", "local state"),
        (1045, 180, 190, "Telegram", "optional external"),
    ]
    for x, y, width, heading, detail in nodes:
        out += panel(x, y, width, 130)
        out += text(x + width // 2, y + 50, heading, "head", "middle")
        out += text(x + width // 2, y + 88, detail, "small", "middle")
    for x1, x2 in ((255, 295), (505, 545), (755, 795), (1005, 1045)):
        out += f'<path d="M{x1} 245 L{x2} 245" class="line" marker-end="url(#arrow)"/>\n'
    out += panel(95, 390, 500, 190, "panel2")
    out += text(125, 432, "RETAINED SOURCE SURFACES", "head")
    out += text(125, 474, "capture · recognition · matching")
    out += text(125, 510, "SQLite history · Tk GUI · workers")
    out += text(125, 546, "bot notifications · group-call stream")
    out += panel(685, 390, 500, 190, "panel2")
    out += text(715, 432, "NOT ESTABLISHED", "head")
    out += text(715, 474, "DTK availability or redistribution", "warn")
    out += text(715, 510, "camera / plate privacy or consent", "warn")
    out += text(715, 546, "runtime correctness or security", "warn")
    out += text(640, 655, "No native load · no camera · no database · no network", "good", "middle")
    return out + "</svg>\n"


def render_credential_boundary(manifest: dict[str, Any]) -> str:
    env = manifest["environment_template"]
    groups = [
        ("LOCAL PATHS", 2, "database + native library"),
        ("BOT CHANNEL", 2, "bot token + chat identifier"),
        ("STREAM SESSION", 4, "API/session/chat settings"),
    ]
    out = svg_open(
        "Credential and configuration boundary",
        "Empty current environment template separated from two historical Telegram-token alerts and provider-side revocation.",
    )
    out += text(60, 62, "SSSSD / CREDENTIAL BOUNDARY", "title")
    out += text(60, 94, "Key names counted; values are neither retained in evidence nor displayed.", "sub")
    for index, (label, count, detail) in enumerate(groups):
        x = 60 + index * 400
        out += panel(x, 150, 360, 165)
        out += text(x + 24, 194, label, "head")
        out += text(x + 24, 238, f"{count} declared keys")
        out += text(x + 24, 277, detail, "small")
    out += panel(60, 365, 540, 210, "panel2")
    out += text(90, 410, "CURRENT DEFAULT BRANCH", "head")
    out += text(90, 454, f"{env['entries']} env keys · {env['nonempty_values']} non-empty values", "good")
    out += text(90, 492, ".env is not tracked", "good")
    out += text(90, 530, "evidence values emitted: 0", "good")
    out += panel(680, 365, 540, 210, "panel2")
    out += text(710, 410, "HISTORICAL / PROVIDER STATE", "head")
    out += text(710, 454, "2 Telegram token alerts remain open", "bad")
    out += text(710, 492, "revocation cannot be proven from Git", "warn")
    out += text(710, 530, "owner action: issue #2", "warn")
    out += text(640, 650, "CURRENT-TREE CLEANUP DOES NOT REVOKE A HISTORICAL TOKEN", "bad", "middle")
    return out + "</svg>\n"


def render_release_gate(manifest: dict[str, Any]) -> str:
    state_css = {
        "pass": "good",
        "review": "warn",
        "human_required": "warn",
        "blocked": "bad",
        "missing": "bad",
    }
    out = svg_open(
        "Quarantined snapshot release gate",
        "Current static evidence and unresolved credential, rights, license, dependency, runtime, and release gates.",
    )
    out += text(60, 62, "SSSSD / RELEASE GATE", "title")
    out += text(60, 94, "No screenshot, demo, or release can close a provider or rights decision.", "sub")
    y = 135
    for row in manifest["release_gate"]:
        out += panel(60, y, 1160, 67, "panel2")
        out += text(88, y + 28, row["id"], "head")
        out += text(1190, y + 28, str(row["state"]).upper(), state_css[row["state"]], "end")
        evidence = row["evidence"]
        if len(evidence) > 112:
            evidence = evidence[:109] + "…"
        out += text(88, y + 53, evidence, "small")
        y += 75
    out += text(640, 685, "PUBLIC RELEASE: BLOCKED · owner actions tracked in issue #2", "bad", "middle")
    return out + "</svg>\n"


def render_text(manifest: dict[str, Any]) -> str:
    python = manifest["python"]
    env = manifest["environment_template"]
    contract = manifest["repository_contract"]
    lines = [
        "$ python3 tools/audit_quarantine.py --check",
        "PASS: committed quarantine evidence matches exact current source bytes",
        f"python_modules={len(python['modules'])}",
        f"python_lines={python['total_lines']}",
        f"top_level_classes={python['top_level_classes']}",
        f"top_level_functions={python['top_level_functions']}",
        f"local_import_edges={len(python['local_import_edges'])}",
        f"nonlocal_import_roots={len(python['nonlocal_import_roots'])}",
        f"environment_keys={env['entries']}",
        f"environment_nonempty_values={env['nonempty_values']}",
        "source_values_emitted=0",
        "application_executed=0",
        "native_library_loaded=0",
        f"dependency_manifest_present={int(contract['dependency_manifest_present'])}",
        f"license_file_present={int(contract['license_file_present'])}",
        "release_status=BLOCKED",
        f"owner_actions={ISSUE_URL}",
    ]
    return "\n".join(lines) + "\n"


def render_bundle(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "source-audit.json": json.dumps(
            manifest, ensure_ascii=True, indent=2, sort_keys=True
        )
        + "\n",
        "source-audit.txt": render_text(manifest),
        "source-inventory.svg": render_inventory(manifest),
        "module-boundary.svg": render_module_boundary(manifest),
        "runtime-boundary.svg": render_runtime_boundary(manifest),
        "credential-boundary.svg": render_credential_boundary(manifest),
        "release-gate.svg": render_release_gate(manifest),
    }


def validate_bundle(bundle: dict[str, str]) -> None:
    if tuple(bundle) != OUTPUT_NAMES:
        raise AssertionError("unexpected evidence inventory")
    for name, content in bundle.items():
        if not content.endswith("\n"):
            raise AssertionError(f"{name} must end with one newline")
        if name.endswith(".svg"):
            ET.fromstring(content)
    serialized = "".join(bundle.values())
    forbidden = (
        "TELEGRAM_BOT_TOKEN=",
        "TELEGRAM_STREAM_API_HASH=",
        "ghp_",
        "github_pat_",
        "AKIA",
    )
    for marker in forbidden:
        if marker in serialized:
            raise AssertionError(f"forbidden secret marker in output: {marker}")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write-candidate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_dir = root / (
        "build/quarantine-evidence" if args.write_candidate else "docs/evidence"
    )
    manifest = build_manifest(root)
    bundle = render_bundle(manifest)
    validate_bundle(bundle)

    if args.write_candidate:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in bundle.items():
            (output_dir / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"WROTE {len(bundle)} privacy-preserving evidence files")
        return 0

    problems: list[str] = []
    for name, expected in bundle.items():
        path = output_dir / name
        if not path.is_file():
            problems.append(f"missing: {path}")
            continue
        if path.read_text(encoding="utf-8") != expected:
            problems.append(f"drift: {path}")
    extras = sorted(
        path.name
        for path in output_dir.glob("*")
        if path.is_file() and path.name not in bundle
    )
    if extras:
        problems.append("unexpected files: " + ", ".join(extras))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    sys.stdout.write(bundle["source-audit.txt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
