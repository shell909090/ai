#!/usr/bin/env python3
"""通用 Python 项目调用图 + 符号签名分析工具。"""

import argparse
import ast
import fnmatch
import logging
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

NODE_COLOR = "#e8e8f0"


@dataclass
class Symbol:
    uid: str          # e.g. "rel/file.py::ClassName.method::42"
    short_name: str   # e.g. "ClassName.method" / "func_name" / "lambda@42"
    file: Path
    lineno: int
    end_lineno: int
    signature: str
    docstring: str | None
    is_async: bool
    kind: str         # "function" | "method" | "lambda"


def collect_files(path: Path, exclude: list[str] | None = None) -> list[Path]:
    """Return all .py files under path, skipping paths matching any exclude glob."""
    candidates = [path] if path.is_file() else sorted(path.rglob("*.py"))
    if not exclude:
        return candidates
    result: list[Path] = []
    for f in candidates:
        parts = f.parts
        if any(fnmatch.fnmatch(str(f), pat) or any(fnmatch.fnmatch(p, pat) for p in parts)
               for pat in exclude):
            log.debug("Excluded: %s", f)
            continue
        result.append(f)
    return result


def _get_docstring(node: ast.AST) -> str | None:
    """Extract first string constant from a function body as docstring."""
    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        val = body[0].value.value
        if isinstance(val, str):
            lines = val.strip().splitlines()
            return lines[0] if lines else None
    return None


def _sig_from_funcdef(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstruct def/async def signature string from AST node."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){ret}"


def _sig_from_lambda(node: ast.Lambda, name: str) -> str:
    """Reconstruct lambda signature string."""
    args = ast.unparse(node.args)
    return f"{name} = lambda {args}: ..."


def _collect_class_map(tree: ast.Module) -> dict[int, str]:
    """Return lineno -> class_name for every method in the module."""
    result: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[item.lineno] = node.name
    return result


def _collect_funcdef(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: Path,
    file: Path,
    class_by_lineno: dict[int, str],
    symbols: list[Symbol],
    skip_private: bool = False,
) -> None:
    """Append a Symbol for a top-level function or class method."""
    class_name = class_by_lineno.get(node.lineno)
    if class_name:
        short_name = f"{class_name}.{node.name}"
        kind = "method"
    elif node.col_offset == 0:
        short_name = node.name
        kind = "function"
    else:
        return  # nested function — skip
    if skip_private and node.name.startswith("_"):
        return
    uid = f"{rel}::{short_name}::{node.lineno}"
    symbols.append(Symbol(
        uid=uid,
        short_name=short_name,
        file=file,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", node.lineno),
        signature=_sig_from_funcdef(node),
        docstring=_get_docstring(node),
        is_async=isinstance(node, ast.AsyncFunctionDef),
        kind=kind,
    ))


def _collect_lambda_assign(
    node: ast.Assign,
    rel: Path,
    file: Path,
    symbols: list[Symbol],
    skip_private: bool = False,
) -> None:
    """Append a Symbol for a lambda found in an Assign node."""
    if not isinstance(node.value, ast.Lambda):
        return
    lam = node.value
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
    else:
        name = f"lambda@{lam.lineno}"
    if skip_private and name.startswith("_"):
        return
    uid = f"{rel}::{name}::{lam.lineno}"
    symbols.append(Symbol(
        uid=uid,
        short_name=name,
        file=file,
        lineno=lam.lineno,
        end_lineno=getattr(lam, "end_lineno", lam.lineno),
        signature=_sig_from_lambda(lam, name),
        docstring=None,
        is_async=False,
        kind="lambda",
    ))


def _collect_lambda_annassign(
    node: ast.AnnAssign,
    rel: Path,
    file: Path,
    symbols: list[Symbol],
    skip_private: bool = False,
) -> None:
    """Append a Symbol for a lambda found in an AnnAssign node."""
    if node.value is None or not isinstance(node.value, ast.Lambda):
        return
    lam = node.value
    name = node.target.id if isinstance(node.target, ast.Name) else f"lambda@{lam.lineno}"
    if skip_private and name.startswith("_"):
        return
    uid = f"{rel}::{name}::{lam.lineno}"
    symbols.append(Symbol(
        uid=uid,
        short_name=name,
        file=file,
        lineno=lam.lineno,
        end_lineno=getattr(lam, "end_lineno", lam.lineno),
        signature=_sig_from_lambda(lam, name),
        docstring=None,
        is_async=False,
        kind="lambda",
    ))


def _extract_from_file(
    file: Path,
    root: Path,
    tree: ast.Module,
    skip_private: bool = False,
) -> list[Symbol]:
    """Extract all function, method, and named-lambda symbols from a parsed AST."""
    rel = file.relative_to(root)
    symbols: list[Symbol] = []
    class_by_lineno = _collect_class_map(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect_funcdef(node, rel, file, class_by_lineno, symbols, skip_private)
        elif isinstance(node, ast.Assign):
            _collect_lambda_assign(node, rel, file, symbols, skip_private)
        elif isinstance(node, ast.AnnAssign):
            _collect_lambda_annassign(node, rel, file, symbols, skip_private)
    return symbols


def _build_name_index(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    """Build short_name (and last segment) → [Symbol] lookup table."""
    index: dict[str, list[Symbol]] = {}
    for sym in symbols:
        index.setdefault(sym.short_name, []).append(sym)
        last = sym.short_name.split(".")[-1]
        if last != sym.short_name:
            index.setdefault(last, []).append(sym)
    return index


def _resolve_call(
    node: ast.Call,
    caller: Symbol,
    var_types: dict[str, str],
    index: dict[str, list[Symbol]],
    by_file_short: dict[tuple[Path, str], list[Symbol]],
    unique_last: dict[str, Symbol | None],
) -> list[str]:
    """Return likely callee UIDs using conservative resolution to avoid false links."""
    func = node.func
    caller_class = caller.short_name.split(".")[0] if caller.kind == "method" else None
    if isinstance(func, ast.Name):
        name = func.id
        # Prefer exact symbol in same file.
        in_file = by_file_short.get((caller.file, name), [])
        if in_file:
            return [s.uid for s in in_file]
        # Inside class methods, allow implicit same-class method calls.
        if caller_class:
            same_class = by_file_short.get((caller.file, f"{caller_class}.{name}"), [])
            if same_class:
                return [s.uid for s in same_class]
        # Fall back to globally unique exact symbol.
        exact = index.get(name, [])
        if len(exact) == 1:
            return [exact[0].uid]
        return []
    if isinstance(func, ast.Attribute):
        attr = func.attr
        if isinstance(func.value, ast.Name):
            owner_name = func.value.id
            if owner_name in {"self", "cls"} and caller_class:
                same_class = by_file_short.get((caller.file, f"{caller_class}.{attr}"), [])
                if same_class:
                    return [s.uid for s in same_class]
            # Resolve typed variables (e.g. `service: RetrievalService`).
            type_name = var_types.get(owner_name)
            if type_name:
                exact_typed = index.get(f"{type_name}.{attr}", [])
                if len(exact_typed) == 1:
                    return [exact_typed[0].uid]
                in_file_typed = by_file_short.get((caller.file, f"{type_name}.{attr}"), [])
                if len(in_file_typed) == 1:
                    return [in_file_typed[0].uid]
        # For object.attr(...), only resolve when this method name is unique project-wide.
        unique = unique_last.get(attr)
        return [unique.uid] if unique is not None else []
    return []


def _iter_calls(root: ast.AST) -> list[ast.Call]:
    """Collect Call nodes but skip nested defs/classes to reduce false edges."""
    calls: list[ast.Call] = []
    stack: list[ast.AST] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Call):
            calls.append(node)
        for child in ast.iter_child_nodes(node):
            if child is not root and isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                continue
            stack.append(child)
    return calls


def _find_func_node(
    tree: ast.Module,
    sym: Symbol,
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | None:
    """Find the AST node for a symbol by matching its start line number."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno == sym.lineno:
                return node
        elif isinstance(node, ast.Lambda) and sym.kind == "lambda":
            if node.lineno == sym.lineno:
                return node
    return None


def _annotation_type_name(node: ast.AST | None) -> str | None:
    """Best-effort extraction of a class/type name from an annotation AST."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        # Prefer inner type for Optional[T], list[T], etc.
        inner = _annotation_type_name(node.slice)
        return inner or _annotation_type_name(node.value)
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            name = _annotation_type_name(elt)
            if name and name != "None":
                return name
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _annotation_type_name(node.left)
        right = _annotation_type_name(node.right)
        if left and left != "None":
            return left
        if right and right != "None":
            return right
    return None


def _collect_var_types(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
) -> dict[str, str]:
    """Collect variable -> annotated type name from function parameters and local AnnAssign."""
    if isinstance(node, ast.Lambda):
        return {}
    var_types: dict[str, str] = {}
    all_args = (
        node.args.posonlyargs
        + node.args.args
        + node.args.kwonlyargs
    )
    for arg in all_args:
        if not arg.arg:
            continue
        typ = _annotation_type_name(arg.annotation)
        if typ:
            var_types[arg.arg] = typ
    if node.args.vararg:
        typ = _annotation_type_name(node.args.vararg.annotation)
        if typ:
            var_types[node.args.vararg.arg] = typ
    if node.args.kwarg:
        typ = _annotation_type_name(node.args.kwarg.annotation)
        if typ:
            var_types[node.args.kwarg.arg] = typ
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            typ = _annotation_type_name(stmt.annotation)
            if typ:
                var_types[stmt.target.id] = typ
    return var_types


def extract_edges(
    symbols: list[Symbol],
    trees: dict[Path, ast.Module],
) -> list[tuple[str, str]]:
    """Walk symbol bodies and return (caller_uid, callee_uid) call edges."""
    index = _build_name_index(symbols)
    by_file_short: dict[tuple[Path, str], list[Symbol]] = defaultdict(list)
    by_last: dict[str, list[Symbol]] = defaultdict(list)
    for s in symbols:
        by_file_short[(s.file, s.short_name)].append(s)
        by_last[s.short_name.split(".")[-1]].append(s)
    unique_last: dict[str, Symbol | None] = {
        name: vals[0] if len(vals) == 1 else None for name, vals in by_last.items()
    }
    uid_set = {s.uid for s in symbols}
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for sym in symbols:
        tree = trees.get(sym.file)
        if tree is None:
            continue
        func_node = _find_func_node(tree, sym)
        if func_node is None:
            continue
        var_types = _collect_var_types(func_node)
        for node in _iter_calls(func_node):
            for callee_uid in _resolve_call(
                node, sym, var_types, index, by_file_short, unique_last
            ):
                if callee_uid == sym.uid:
                    continue
                if callee_uid not in uid_set:
                    continue
                edge = (sym.uid, callee_uid)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
    return edges


def _dot_cluster_id(rel: Path) -> str:
    """Return a safe DOT subgraph cluster id from a relative path."""
    return "cluster_" + str(rel).replace("/", "_").replace("\\", "_").replace(".", "_")


def write_dot(
    symbols: list[Symbol],
    edges: list[tuple[str, str]],
    out: Path,
    root: Path,
) -> None:
    """Write a Graphviz DOT file with file clusters; entry nodes get thick border."""
    callees = {dst for _, dst in edges}
    by_file: dict[Path, list[Symbol]] = defaultdict(list)
    for sym in symbols:
        by_file[sym.file].append(sym)

    lines = [
        "digraph callgraph {",
        '    graph [rankdir=TB fontname="Helvetica" splines=spline nodesep=0.2 ranksep=0.35 '
        'pad=0.1 margin=0 overlap=false newrank=true concentrate=true]',
        '    node  [shape=box style="rounded,filled" fontname="Helvetica"'
        ' fontsize=11 margin="0.12,0.06"]',
        '    edge  [color="#222222" penwidth=1.4 arrowsize=0.8]',
        "",
    ]
    for file in sorted(by_file):
        rel = file.relative_to(root)
        cid = _dot_cluster_id(rel)
        label = str(rel).replace("\\", "/")
        lines += [
            f"    subgraph {cid} {{",
            f'        label="{label}"',
            '        style="rounded"',
            '        color="#aaaacc"',
            '        fontname="Helvetica"',
            '        fontsize=10',
            '        margin=8',
        ]
        for sym in sorted(by_file[file], key=lambda s: s.lineno):
            uid_q = sym.uid.replace('"', '\\"')
            label_q = sym.short_name.replace('"', '\\"')
            penwidth = "1.0" if sym.uid in callees else "2.5"
            lines.append(
                f'        "{uid_q}" [label="{label_q}"'
                f' fillcolor="{NODE_COLOR}" penwidth={penwidth}]'
            )
        lines.append("    }")
        lines.append("")

    for src, dst in edges:
        src_q = src.replace('"', '\\"')
        dst_q = dst.replace('"', '\\"')
        lines.append(f'    "{src_q}" -> "{dst_q}"')
    lines.append("}")
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("[ok] %s written", out)


def write_svg(
    symbols: list[Symbol],
    edges: list[tuple[str, str]],
    out: Path,
    root: Path,
    dot_path: Path | None = None,
) -> None:
    """Render call graph to SVG via Graphviz `dot` for stable layout and routing."""
    dot_bin = shutil.which("dot")
    if not dot_bin:
        raise RuntimeError("Graphviz `dot` not found in PATH.")

    cleanup_tmp = False
    if dot_path is None:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".dot", delete=False, encoding="utf-8"
        )
        tmp.close()
        dot_path = Path(tmp.name)
        write_dot(symbols, edges, dot_path, root)
        cleanup_tmp = True

    cmd = [dot_bin, "-Tsvg", str(dot_path), "-o", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "").strip()
        raise RuntimeError(f"`dot` render failed: {err}") from exc
    finally:
        if cleanup_tmp and dot_path.exists():
            dot_path.unlink()

    log.info("[ok] %s written", out)


def write_signatures_md(
    symbols: list[Symbol],
    root: Path,
    out: Path,
) -> None:
    """Write summary + per-file pseudo-code signature blocks to Markdown."""
    n_func = sum(1 for s in symbols if s.kind == "function")
    n_meth = sum(1 for s in symbols if s.kind == "method")
    n_lamb = sum(1 for s in symbols if s.kind == "lambda")
    by_file: dict[Path, list[Symbol]] = defaultdict(list)
    for sym in symbols:
        by_file[sym.file].append(sym)

    lines = [
        "# Symbol Reference",
        "",
        f"Analyzed: **{len(by_file)} files** | "
        f"**{len(symbols)} symbols** "
        f"({n_func} functions, {n_meth} methods, {n_lamb} lambdas)",
        "",
    ]
    lines += ["## By File", ""]
    for file in sorted(by_file):
        rel = file.relative_to(root)
        file_symbols = sorted(by_file[file], key=lambda s: s.lineno)
        module_funcs = [sym for sym in file_symbols if sym.kind != "method"]
        class_methods: dict[str, list[Symbol]] = defaultdict(list)
        for sym in file_symbols:
            if sym.kind == "method":
                class_name = sym.short_name.split(".", 1)[0]
                class_methods[class_name].append(sym)

        lines += [f"### {rel}", "", "```python"]
        for sym in module_funcs:
            lines.extend(_render_symbol_block(sym))
            lines.append("")
        for class_name in sorted(class_methods):
            lines.append(f"class {class_name}:")
            for method in class_methods[class_name]:
                for entry in _render_symbol_block(method, indent="    ", in_class=True):
                    lines.append(entry)
                lines.append("")
        if lines[-1] == "":
            lines.pop()
        lines += ["```", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("[ok] %s written", out)


def _render_symbol_block(
    sym: Symbol,
    indent: str = "",
    in_class: bool = False,
) -> list[str]:
    """Render one symbol as a concise pseudo-code block."""
    signature = sym.signature
    if in_class and "." in sym.short_name:
        _, method_name = sym.short_name.split(".", 1)
        signature = signature.replace(f" {method_name}(", f" {method_name}(", 1)
    lines = [f"{indent}{signature}: ..."]
    if sym.docstring:
        doc = sym.docstring.replace('"""', '\\"\\"\\"')
        lines.append(f'{indent}    """{doc}"""')
    return lines


def main() -> None:
    """CLI entry: analyze Python files and emit callgraph.dot, .svg, signatures.md."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Analyze a Python project: generate call graph and symbol table."
    )
    parser.add_argument("path", type=Path, help=".py file or directory (recursive)")
    parser.add_argument(
        "--out", type=Path, default=Path("."), metavar="DIR",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB",
        help="Exclude files matching glob pattern (repeatable, e.g. '*/tests/*')",
    )
    parser.add_argument(
        "--output", choices=["dot", "svg", "md", "all"], default="all",
        help="Outputs to generate (default: all)",
    )
    parser.add_argument(
        "--no-private", action="store_true",
        help="Skip symbols whose name starts with '_'",
    )
    args = parser.parse_args()

    files = collect_files(args.path, exclude=args.exclude or None)
    if not files:
        log.error("No .py files found at %s", args.path)
        return
    root = args.path if args.path.is_dir() else args.path.parent
    trees: dict[Path, ast.Module] = {}
    for f in files:
        try:
            trees[f] = ast.parse(
                f.read_text(encoding="utf-8", errors="replace"), filename=str(f)
            )
        except SyntaxError:
            log.warning("Skipping %s: syntax error", f)

    skip_private: bool = args.no_private
    symbols: list[Symbol] = []
    for f, tree in trees.items():
        symbols.extend(_extract_from_file(f, root, tree, skip_private))
    log.info("Found %d symbols in %d files", len(symbols), len(trees))

    edges = extract_edges(symbols, trees)
    log.info("Found %d call edges", len(edges))

    want = args.output
    args.out.mkdir(parents=True, exist_ok=True)
    dot_out = args.out / "callgraph.dot"
    if want in ("dot", "all"):
        write_dot(symbols, edges, dot_out, root)
    if want in ("svg", "all"):
        write_svg(
            symbols,
            edges,
            args.out / "callgraph.svg",
            root,
            dot_out if dot_out.exists() else None,
        )
    if want in ("md", "all"):
        write_signatures_md(symbols, root, args.out / "signatures.md")


if __name__ == "__main__":
    main()
