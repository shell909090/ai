#!/usr/bin/env python3
"""
Generate a monthly KEV-focused vulnerability report against local and custom software inventory.

Highlights:
- Pulls CISA KEV feed and keeps only entries added in the last N days (default: 31).
- Builds inventory from multiple sources (dpkg/rpm/apk/pip/npm/gem + custom files).
- Resolves affected software and minimum safe version using OSV first, NVD fallback.
- Persists feed and API responses in a local cache directory (GitHub Actions cache-friendly).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterable

_CPE_MIN_PARTS = 5
_FUZZY_MIN_LEN = 4

logger = logging.getLogger(__name__)

OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{cve}"
NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve}"
TELEGRAM_CHUNK_SIZE = 3996


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class VulnEntry:
    """Raw vulnerability entry returned by a data source."""

    cve_id: str
    date_added: str
    vendor_project: str
    product: str
    required_action: str
    due_date: str
    notes: str


@dataclass
class InventoryItem:
    name: str
    version: str
    source: str
    aliases: list[str]


@dataclass
class AffectedSoftware:
    software: str
    ecosystem: str
    min_safe_version: str
    evidence_source: str


@dataclass
class ReportRow:
    cve_id: str
    date_added: str
    kev_vendor_project: str
    kev_product: str
    kev_required_action: str
    kev_due_date: str
    kev_notes: str
    matched_local_software: list[str]
    affected_software: list[AffectedSoftware]


@dataclass
class SoftwareSummary:
    """Aggregated per-software entry across all CVEs."""

    software: str
    ecosystem: str
    min_safe_version: str
    cve_ids: list[str]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def utc_today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_json(path: Path, obj: Any) -> None:
    """Write obj as JSON to path, creating parent dirs."""
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _cache_age_seconds(cache_file: Path) -> float:
    """Return seconds since cache_file was last modified."""
    mtime = dt.datetime.fromtimestamp(cache_file.stat().st_mtime, tz=dt.UTC)
    return (dt.datetime.now(tz=dt.UTC) - mtime).total_seconds()


def fetch_text_cached(url: str, cache_file: Path, ttl_hours: int = 24) -> str:
    """Fetch URL text, returning cached copy if still fresh."""
    ensure_dir(cache_file.parent)
    if cache_file.exists() and _cache_age_seconds(cache_file) < ttl_hours * 3600:
        return cache_file.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "kev-report/1.0"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        content = resp.read().decode("utf-8", errors="replace")
    cache_file.write_text(content, encoding="utf-8")
    return content


def fetch_json_cached(url: str, cache_file: Path, ttl_hours: int = 168) -> dict[str, Any]:
    """Fetch URL JSON, returning cached copy if still fresh."""
    ensure_dir(cache_file.parent)
    if cache_file.exists() and _cache_age_seconds(cache_file) < ttl_hours * 3600:
        return read_json(cache_file, {})
    req = urllib.request.Request(url, headers={"User-Agent": "kev-report/1.0"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=40) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    write_json(cache_file, payload)
    return payload


# ---------------------------------------------------------------------------
# Data source abstraction
# ---------------------------------------------------------------------------


class Source(ABC):
    """Abstract base class for vulnerability data sources."""

    @abstractmethod
    def fetch(
        self, window_days: int, today: dt.date, cache_dir: Path, ttl_hours: int,
    ) -> list[VulnEntry]:
        """Return vulnerability entries added within window_days of today."""
        ...


class KevSource(Source):
    """CISA Known Exploited Vulnerabilities (KEV) CSV data source."""

    URLS: ClassVar[list[str]] = [
        "https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv",
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.csv",
    ]

    def fetch(
        self, window_days: int, today: dt.date, cache_dir: Path, ttl_hours: int,
    ) -> list[VulnEntry]:
        """Fetch KEV CSV feed and filter to the time window."""
        csv_text = self._fetch_csv(cache_dir, ttl_hours)
        return self._parse(csv_text, window_days, today)

    def _fetch_csv(self, cache_dir: Path, ttl_hours: int) -> str:
        last_err: Exception | None = None
        for idx, url in enumerate(self.URLS, start=1):
            try:
                return fetch_text_cached(
                    url, cache_dir / "feeds" / f"kev_{idx}.csv", ttl_hours=ttl_hours,
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
        if last_err:
            raise last_err
        msg = "No KEV feed URLs configured"
        raise RuntimeError(msg)

    def _parse(self, csv_text: str, window_days: int, today: dt.date) -> list[VulnEntry]:
        entries: list[VulnEntry] = []
        start_date = today - dt.timedelta(days=window_days)
        reader = csv.DictReader(csv_text.splitlines())
        for r in reader:
            d = (r.get("dateAdded") or "").strip()
            if not d:
                continue
            try:
                date_added = dt.datetime.strptime(d, "%Y-%m-%d").date()  # noqa: DTZ007
            except ValueError:
                continue
            if not (start_date <= date_added <= today):
                continue
            cve_id = (r.get("cveID") or "").strip()
            if not cve_id:
                continue
            entries.append(
                VulnEntry(
                    cve_id=cve_id,
                    date_added=d,
                    vendor_project=(r.get("vendorProject") or "").strip(),
                    product=(r.get("product") or "").strip(),
                    required_action=(r.get("requiredAction") or "").strip(),
                    due_date=(r.get("dueDate") or "").strip(),
                    notes=(r.get("notes") or "").strip(),
                ),
            )
        return entries


# ---------------------------------------------------------------------------
# Inventory collection
# ---------------------------------------------------------------------------


def _inv_dpkg() -> list[InventoryItem]:
    """Collect Debian packages via dpkg-query."""
    if not shutil.which("dpkg-query"):
        return []
    rc, out, _ = run_cmd(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"])
    if rc != 0:
        return []
    items = []
    for line in out.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        n, v = line.split("\t", 1)
        items.append(InventoryItem(n.strip(), v.strip(), "dpkg", []))
    return items


def _inv_rpm() -> list[InventoryItem]:
    """Collect RPM packages."""
    if not shutil.which("rpm"):
        return []
    rc, out, _ = run_cmd(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\n"])
    if rc != 0:
        return []
    return [
        InventoryItem(n.strip(), v.strip(), "rpm", [])
        for line in out.splitlines()
        if "\t" in line
        for n, v in [line.split("\t", 1)]
    ]


def _inv_apk() -> list[InventoryItem]:
    """Collect Alpine packages via apk."""
    if not shutil.which("apk"):
        return []
    rc, out, _ = run_cmd(["apk", "info", "-v"])
    if rc != 0:
        return []
    items = []
    for raw in out.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        m = re.match(r"^(.*)-([0-9].*)$", stripped)
        if m:
            items.append(InventoryItem(m.group(1), m.group(2), "apk", []))
    return items


def _inv_pip() -> list[InventoryItem]:
    """Collect Python packages via pip list."""
    if not shutil.which("python3"):
        return []
    rc, out, _ = run_cmd(["python3", "-m", "pip", "list", "--format=json"])
    if rc != 0:
        return []
    try:
        return [
            InventoryItem(p.get("name", ""), p.get("version", ""), "pip", [])
            for p in json.loads(out)
        ]
    except Exception:  # noqa: BLE001
        return []


def _inv_npm() -> list[InventoryItem]:
    """Collect global npm packages."""
    if not shutil.which("npm"):
        return []
    rc, out, _ = run_cmd(["npm", "ls", "-g", "--depth=0", "--json"])
    if rc != 0:
        return []
    try:
        deps = json.loads(out).get("dependencies", {})
        return [
            InventoryItem(name, str(data.get("version", "")), "npm-global", [])
            for name, data in deps.items()
        ]
    except Exception:  # noqa: BLE001
        return []


def _inv_gem() -> list[InventoryItem]:
    """Collect Ruby gems."""
    if not shutil.which("gem"):
        return []
    rc, out, _ = run_cmd(["gem", "list", "--local"])
    if rc != 0:
        return []
    items = []
    for line in out.splitlines():
        m = re.match(r"^([\w\-]+) \(([^)]+)\)", line.strip())
        if m:
            versions = m.group(2).split(",")
            items.append(InventoryItem(m.group(1), versions[0].strip(), "gem", []))
    return items


def collect_inventory_auto() -> list[InventoryItem]:
    """Collect installed packages from dpkg/rpm/apk/pip/npm/gem."""
    items: list[InventoryItem] = []
    for collector in (_inv_dpkg, _inv_rpm, _inv_apk, _inv_pip, _inv_npm, _inv_gem):
        items.extend(collector())
    return dedup_inventory(items)


def _parse_inv_csv(path: Path) -> list[InventoryItem]:
    """Parse inventory from a CSV file with name/version/source/aliases columns."""
    items = []
    with path.open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            version = (r.get("version") or "").strip()
            source = (r.get("source") or f"file:{path.name}").strip()
            raw_aliases = (r.get("aliases") or "").strip()
            aliases = [a.strip() for a in raw_aliases.split("|") if a.strip()] if raw_aliases else []
            items.append(InventoryItem(name, version, source, aliases))
    return items


def _parse_inv_json(path: Path) -> list[InventoryItem]:
    """Parse inventory from JSON (CycloneDX, SPDX, or generic list)."""
    data = read_json(path, {})

    if isinstance(data, dict) and data.get("bomFormat") == "CycloneDX":
        return [
            InventoryItem(
                str(comp.get("name", "")).strip(),
                str(comp.get("version", "")).strip(),
                f"cyclonedx:{path.name}",
                [str(comp[k]) for k in ("purl", "cpe") if comp.get(k)],
            )
            for comp in data.get("components", [])
            if str(comp.get("name", "")).strip()
        ]

    if isinstance(data, dict) and data.get("spdxVersion"):
        items = []
        for pkg in data.get("packages", []):
            name = str(pkg.get("name", "")).strip()
            if not name:
                continue
            ext = pkg.get("externalRefs", [])
            aliases = [
                str(r["referenceLocator"])
                for r in (ext if isinstance(ext, list) else [])
                if isinstance(r, dict) and r.get("referenceLocator")
            ]
            items.append(InventoryItem(name, str(pkg.get("versionInfo", "")).strip(), f"spdx:{path.name}", aliases))
        return items

    if isinstance(data, list):
        items = []
        for row in data:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            aliases_raw = row.get("aliases", [])
            aliases = [str(a).strip() for a in aliases_raw if str(a).strip()] if isinstance(aliases_raw, list) else []
            version = str(row.get("version", "")).strip()
            source = str(row.get("source", f"file:{path.name}")).strip()
            items.append(InventoryItem(name, version, source, aliases))
        return items

    return []


def _parse_inv_text(path: Path) -> list[InventoryItem]:
    """Parse inventory from plain text (one 'name version' or 'name:version' per line)."""
    items = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, version = line.split(":", 1)
            else:
                parts = line.split()
                name = parts[0]
                version = parts[1] if len(parts) > 1 else ""
            items.append(InventoryItem(name.strip(), version.strip(), f"file:{path.name}", []))
    return items


def parse_inventory_file(path: Path) -> list[InventoryItem]:
    """Parse inventory from CSV, JSON (CycloneDX/SPDX/generic), or plain text."""
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        return _parse_inv_csv(path)
    if path.suffix.lower() == ".json":
        return _parse_inv_json(path)
    return _parse_inv_text(path)


def dedup_inventory(items: list[InventoryItem]) -> list[InventoryItem]:
    """Merge duplicate inventory items, combining aliases and sources."""
    merged: dict[tuple[str, str], InventoryItem] = {}
    for i in items:
        if not i.name:
            continue
        key = (normalize_name(i.name), i.version)
        if key not in merged:
            merged[key] = i
        else:
            cur = merged[key]
            cur.aliases = sorted(set(cur.aliases + i.aliases))
            if i.source not in cur.source:
                cur.source = f"{cur.source}|{i.source}"
    return list(merged.values())


# ---------------------------------------------------------------------------
# Vulnerability detail resolution (OSV + NVD)
# ---------------------------------------------------------------------------


def _max_version_of(versions: list[str]) -> str:
    """Return the highest version from a list, treating unknown as lowest."""
    result = "unknown"
    for v in versions:
        result = max_version(result, v)
    return result


def extract_from_osv(osv: dict[str, Any]) -> list[AffectedSoftware]:
    """Extract affected software and fixed versions from an OSV response.

    Each range represents an affected branch; we take the min fixed within each
    branch then the max across branches to avoid under-reporting for newer branches.
    """
    out: list[AffectedSoftware] = []
    affected = osv.get("affected", []) if isinstance(osv, dict) else []
    for a in affected:
        pkg = a.get("package", {}) if isinstance(a, dict) else {}
        name = str(pkg.get("name", "")).strip()
        eco = str(pkg.get("ecosystem", "")).strip()
        if not name:
            continue
        branch_fixes: list[str] = []
        for rng in a.get("ranges", []) or []:
            events = rng.get("events", []) if isinstance(rng, dict) else []
            rng_fixed = [str(e["fixed"]) for e in events if isinstance(e, dict) and e.get("fixed")]
            branch_fix = pick_min_version(rng_fixed)
            if branch_fix:
                branch_fixes.append(branch_fix)
        min_safe = _max_version_of(branch_fixes)
        out.append(
            AffectedSoftware(
                software=f"{eco}:{name}" if eco else name,
                ecosystem=eco,
                min_safe_version=min_safe or "unknown",
                evidence_source="OSV",
            ),
        )
    return dedup_affected(out)


def parse_cpe(cpe_uri: str) -> tuple[str, str]:
    # cpe:2.3:a:vendor:product:...
    parts = cpe_uri.split(":")
    if len(parts) >= _CPE_MIN_PARTS and parts[0] == "cpe" and parts[1] == "2.3":
        return parts[3], parts[4]
    return "", ""


def extract_cpe_matches(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for m in node.get("cpeMatch", []) or []:
        if isinstance(m, dict):
            yield m
    for child in node.get("nodes", []) or []:
        if isinstance(child, dict):
            yield from extract_cpe_matches(child)


def extract_from_nvd(nvd: dict[str, Any]) -> list[AffectedSoftware]:
    """Extract affected software from an NVD CVE API response."""
    out: list[AffectedSoftware] = []
    vulns = nvd.get("vulnerabilities", []) if isinstance(nvd, dict) else []
    for v in vulns:
        cve = v.get("cve", {}) if isinstance(v, dict) else {}
        conf = cve.get("configurations", []) if isinstance(cve, dict) else []
        for cfg in conf:
            nodes = cfg.get("nodes", []) if isinstance(cfg, dict) else []
            for n in nodes:
                for m in extract_cpe_matches(n):
                    if not m.get("vulnerable", True):
                        continue
                    crit = str(m.get("criteria", ""))
                    vendor, product = parse_cpe(crit)
                    if not product:
                        continue
                    min_safe = "unknown"
                    if m.get("versionEndExcluding"):
                        min_safe = str(m["versionEndExcluding"])
                    elif m.get("versionEndIncluding"):
                        min_safe = f">{m['versionEndIncluding']}"
                    out.append(
                        AffectedSoftware(
                            software=f"{vendor}:{product}",
                            ecosystem="cpe",
                            min_safe_version=min_safe,
                            evidence_source="NVD",
                        ),
                    )
    return dedup_affected(out)


def resolve_affected(cve_id: str, cache_dir: Path, ttl_hours: int) -> list[AffectedSoftware]:
    """Resolve affected software for a CVE via OSV (primary) + NVD (fallback)."""
    affected: list[AffectedSoftware] = []
    osv_cache = cache_dir / "osv" / f"{cve_id}.json"
    nvd_cache = cache_dir / "nvd" / f"{cve_id}.json"

    try:
        osv_data = fetch_json_cached(
            OSV_VULN_URL.format(cve=urllib.parse.quote(cve_id)), osv_cache, ttl_hours=ttl_hours,
        )
        if osv_data and osv_data.get("id"):
            affected = extract_from_osv(osv_data)
    except urllib.error.HTTPError:
        pass
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        nvd_data = fetch_json_cached(
            NVD_CVE_URL.format(cve=urllib.parse.quote(cve_id)), nvd_cache, ttl_hours=ttl_hours,
        )
        nvd_affected = extract_from_nvd(nvd_data)
        affected = dedup_affected(affected + nvd_affected)
    except Exception:  # noqa: BLE001, S110
        pass

    return affected


# ---------------------------------------------------------------------------
# Version utilities
# ---------------------------------------------------------------------------


def version_key(v: str) -> tuple:
    """Lightweight best-effort version comparator key for dotted version strings."""
    tokens = re.split(r"[.+\-_:]", v)
    out = []
    for t in tokens:
        if t.isdigit():
            out.append((0, int(t)))
        else:
            out.append((1, t))
    return tuple(out)


def pick_min_version(versions: list[str]) -> str:
    """Return the lowest version string from a list."""
    clean = [v for v in versions if v and v.lower() != "0"]
    if not clean:
        return ""
    try:
        return sorted(clean, key=version_key)[0]
    except Exception:  # noqa: BLE001
        return sorted(clean)[0]


def max_version(a: str, b: str) -> str:
    """Return the higher (more restrictive) of two min_safe version strings."""
    if a == "unknown":
        return b
    if b == "unknown":
        return a
    try:
        return a if version_key(a) >= version_key(b) else b
    except Exception:  # noqa: BLE001
        return max(a, b)


def dedup_affected(items: list[AffectedSoftware]) -> list[AffectedSoftware]:
    """Merge duplicate affected software entries, combining evidence sources."""
    merged: dict[tuple[str, str], AffectedSoftware] = {}
    for i in items:
        key = (normalize_name(i.software), i.min_safe_version)
        if key not in merged:
            merged[key] = i
        else:
            cur = merged[key]
            if i.evidence_source not in cur.evidence_source:
                cur.evidence_source = f"{cur.evidence_source}|{i.evidence_source}"
    return list(merged.values())


# ---------------------------------------------------------------------------
# Inventory matching
# ---------------------------------------------------------------------------


def build_name_index(inv: list[InventoryItem]) -> dict[str, list[InventoryItem]]:
    """Build normalized-name lookup index over inventory items and their aliases."""
    idx: dict[str, list[InventoryItem]] = {}
    for i in inv:
        keys = {normalize_name(i.name)}
        for a in i.aliases:
            keys.add(normalize_name(a))
        for k in keys:
            if not k:
                continue
            idx.setdefault(k, []).append(i)
    return idx


def match_inventory(
    affected: list[AffectedSoftware], inv_idx: dict[str, list[InventoryItem]],
) -> list[str]:
    """Return local inventory items matching any affected software entry."""
    matched: dict[str, str] = {}
    inv_keys = list(inv_idx.keys())
    for a in affected:
        n = normalize_name(a.software)
        if not n:
            continue
        candidates = inv_idx.get(n, [])
        if not candidates:
            for k in inv_keys:
                if len(n) >= _FUZZY_MIN_LEN and len(k) >= _FUZZY_MIN_LEN and (n in k or k in n):
                    candidates.extend(inv_idx[k])
        for c in candidates:
            matched[f"{c.name}@{c.version}"] = c.source
    return [f"{k} [{v}]" for k, v in sorted(matched.items())]


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report_rows(
    entries: list[VulnEntry],
    inventory: list[InventoryItem],
    cache_dir: Path,
    vuln_ttl_hours: int,
) -> list[ReportRow]:
    """Build report rows: resolve affected software, filter by inventory if provided."""
    inv_idx = build_name_index(inventory)
    has_inventory = bool(inventory)
    rows: list[ReportRow] = []
    for entry in entries:
        affected = resolve_affected(entry.cve_id, cache_dir, vuln_ttl_hours)
        matched_local = match_inventory(affected, inv_idx) if has_inventory else []
        if has_inventory and not matched_local:
            continue
        rows.append(
            ReportRow(
                cve_id=entry.cve_id,
                date_added=entry.date_added,
                kev_vendor_project=entry.vendor_project,
                kev_product=entry.product,
                kev_required_action=entry.required_action,
                kev_due_date=entry.due_date,
                kev_notes=entry.notes,
                matched_local_software=matched_local,
                affected_software=affected,
            ),
        )
    return rows


def build_summary(
    report_rows: list[ReportRow],
    inv_idx: dict[str, list[InventoryItem]],
) -> list[SoftwareSummary]:
    """Aggregate affected software across CVEs; take max(min_safe_version) per package.

    When inv_idx is non-empty, only include software that matches local inventory.
    """
    has_inventory = bool(inv_idx)
    merged: dict[str, SoftwareSummary] = {}
    for row in report_rows:
        for a in row.affected_software:
            if has_inventory and not match_inventory([a], inv_idx):
                continue
            key = normalize_name(a.software)
            if key not in merged:
                merged[key] = SoftwareSummary(
                    software=a.software,
                    ecosystem=a.ecosystem,
                    min_safe_version=a.min_safe_version,
                    cve_ids=[row.cve_id],
                )
            else:
                cur = merged[key]
                cur.min_safe_version = max_version(cur.min_safe_version, a.min_safe_version)
                if row.cve_id not in cur.cve_ids:
                    cur.cve_ids.append(row.cve_id)
    return sorted(merged.values(), key=lambda x: x.software)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _report_header(
    today: dt.date, window_days: int, inventory_count: int, kev_count: int, extra: str = "",
) -> list[str]:
    return [
        f"# KEV Report{extra} ({today.isoformat()})",
        "",
        f"- Window: last {window_days} days",
        f"- Inventory items: {inventory_count}",
        f"- KEV rows in window: {kev_count}",
    ]


def render_cve_md(
    report_rows: list[ReportRow],
    today: dt.date,
    window_days: int,
    inventory_count: int,
    kev_count: int,
) -> str:
    """Render per-CVE Markdown report."""
    lines = _report_header(today, window_days, inventory_count, kev_count)
    lines.append(f"- Report rows (after inventory filter): {len(report_rows)}")
    lines.append("")

    if not report_rows:
        lines.append("No matching KEV items found for current filter.")
        return "\n".join(lines)

    for r in report_rows:
        lines.append(f"## {r.cve_id}")
        lines.append(f"- Date added: {r.date_added}")
        lines.append(f"- Vendor/Product: {r.kev_vendor_project} / {r.kev_product}")
        lines.append(f"- Required action: {r.kev_required_action}")
        if r.kev_due_date:
            lines.append(f"- KEV due date: {r.kev_due_date}")
        if r.kev_notes:
            lines.append(f"- Notes: {r.kev_notes}")
        if r.matched_local_software:
            lines.append("- Matched local software:")
            for x in r.matched_local_software:
                lines.append(f"  - {x}")
        else:
            lines.append("- Matched local software: none")
        lines.append("- Affected software and minimum safe version:")
        if r.affected_software:
            for a in r.affected_software:
                lines.append(
                    f"  - {a.software} | min_safe_version={a.min_safe_version}"
                    f" | source={a.evidence_source}",
                )
        else:
            lines.append("  - unknown (no OSV/NVD mapping found)")
        lines.append("")

    return "\n".join(lines)


def render_summary_md(  # noqa: PLR0913
    summary: list[SoftwareSummary],
    today: dt.date,
    window_days: int,
    inventory_count: int,
    kev_count: int,
    report_count: int,
) -> str:
    """Render per-software aggregated Markdown report."""
    lines = _report_header(today, window_days, inventory_count, kev_count, extra=" - Summary")
    lines.append(f"- CVEs included: {report_count}")
    lines.append(f"- Unique software packages: {len(summary)}")
    lines.append("")

    if not summary:
        lines.append("No affected software found for current filter.")
        return "\n".join(lines)

    for s in summary:
        lines.append(f"## {s.software}")
        if s.ecosystem:
            lines.append(f"- Ecosystem: {s.ecosystem}")
        lines.append(f"- Minimum safe version: {s.min_safe_version}")
        lines.append(f"- Affected by: {', '.join(s.cve_ids)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output targets
# ---------------------------------------------------------------------------


def _tg_send_chunk(token: str, chat_id: str, text: str) -> None:
    """Send a single Telegram message."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(  # noqa: S310
        url, data=payload, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        resp.read()


def send_telegram(text: str, token: str, chat_ids: list[str]) -> None:
    """Split text into chunks and send to each Telegram chat ID."""
    chunks: list[str] = []
    while text:
        if len(text) <= TELEGRAM_CHUNK_SIZE:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, TELEGRAM_CHUNK_SIZE)
        if split_at <= 0:
            split_at = TELEGRAM_CHUNK_SIZE
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    total = len(chunks)
    for chat_id in chat_ids:
        for i, chunk in enumerate(chunks):
            marker = f"\n({i + 1}/{total})" if total > 1 else ""
            try:
                _tg_send_chunk(token, chat_id, chunk + marker)
            except Exception:
                logger.exception("Telegram send failed for chat %s chunk %d", chat_id, i + 1)


def deliver_report(text: str, args: argparse.Namespace, stamp: str) -> None:
    """Send report text to all configured output targets."""
    if args.output_stdout:
        print(text)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        ensure_dir(output_dir)
        md_out = output_dir / f"kev_report_{stamp}.md"
        md_out.write_text(text, encoding="utf-8")
        logger.info("Generated: %s", md_out)

    if args.output_telegram:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_ids_raw = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_ids_raw:
            logger.warning(
                "Telegram output requested but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set",
            )
        else:
            chat_ids = [c.strip() for c in chat_ids_raw.split(",") if c.strip()]
            send_telegram(text, token, chat_ids)


def _save_json(
    report_rows: list[ReportRow],
    inventory: list[InventoryItem],
    entries: list[VulnEntry],
    args: argparse.Namespace,
    stamp: str,
) -> None:
    """Write JSON report file alongside the Markdown output."""
    output_dir = Path(args.output_dir)
    json_out = output_dir / f"kev_report_{stamp}.json"
    write_json(
        json_out,
        {
            "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            "window_days": args.window_days,
            "inventory_count": len(inventory),
            "kev_entries_in_window": len(entries),
            "report_count": len(report_rows),
            "rows": [
                {**asdict(r), "affected_software": [asdict(a) for a in r.affected_software]}
                for r in report_rows
            ],
        },
    )
    logger.info("Generated: %s", json_out)



# ---------------------------------------------------------------------------
# Main report generation
# ---------------------------------------------------------------------------


def generate_report(args: argparse.Namespace) -> int:
    """Orchestrate data fetch, report build, and delivery."""
    today = utc_today()
    cache_dir = Path(args.cache_dir)
    ensure_dir(cache_dir)

    source = KevSource()
    entries = source.fetch(args.window_days, today, cache_dir, args.feed_ttl_hours)

    inventory: list[InventoryItem] = []
    if not args.no_auto_inventory:
        inventory.extend(collect_inventory_auto())
    for p in args.inventory_file:
        inventory.extend(parse_inventory_file(Path(p)))
    inventory = dedup_inventory(inventory)

    inv_idx = build_name_index(inventory)
    report_rows = build_report_rows(entries, inventory, cache_dir, args.vuln_ttl_hours)
    stamp = today.strftime("%Y%m%d")

    if args.mode == "summary":
        summary = build_summary(report_rows, inv_idx)
        text = render_summary_md(
            summary, today, args.window_days, len(inventory), len(entries), len(report_rows),
        )
    else:
        text = render_cve_md(report_rows, today, args.window_days, len(inventory), len(entries))

    deliver_report(text, args, stamp)

    if args.output_dir:
        _save_json(report_rows, inventory, entries, args, stamp)

    logger.info(
        "Rows: %d (window KEV rows=%d, inventory=%d)",
        len(report_rows),
        len(entries),
        len(inventory),
    )

    if args.fail_on_hits and report_rows:
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate monthly KEV report with minimum safe versions.")
    p.add_argument(
        "--window-days", type=int, default=31,
        help="Only include KEV entries added in this window (default: 31).",
    )
    p.add_argument(
        "--cache-dir", default=".cache/kev-report",
        help="Cache directory for feeds, CVE metadata, and history.",
    )
    p.add_argument(
        "--inventory-file", action="append", default=[],
        help="Optional inventory file(s): CSV/JSON/TXT, repeatable.",
    )
    p.add_argument(
        "--no-auto-inventory", action="store_true",
        help="Disable local auto inventory collection.",
    )
    p.add_argument(
        "--feed-ttl-hours", type=int, default=24,
        help="KEV feed cache TTL (hours).",
    )
    p.add_argument(
        "--vuln-ttl-hours", type=int, default=168,
        help="OSV/NVD cache TTL (hours).",
    )
    p.add_argument(
        "--fail-on-hits", action="store_true",
        help="Exit with code 2 if report has matches.",
    )
    p.add_argument(
        "--mode", choices=["cve", "summary"], default="cve",
        help="Output mode: per-CVE list (default) or aggregated software summary.",
    )
    p.add_argument(
        "--output-stdout", action="store_true",
        help="Print report to stdout.",
    )
    p.add_argument(
        "--output-dir", default=None,
        help="Directory for markdown/json report files (omit to skip file output).",
    )
    p.add_argument(
        "--output-telegram", action="store_true",
        help="Send report via Telegram (requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars).",
    )
    return p.parse_args()


def setup_logging() -> None:
    """Configure root logger to INFO with timestamp."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def main() -> int:
    setup_logging()
    args = parse_args()
    try:
        return generate_report(args)
    except KeyboardInterrupt:
        return 130
    except Exception:
        logger.exception("ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
