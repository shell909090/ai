"""Regression tests for KEV parsing, matching, and report rendering."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import kev_report as kev


class KevParsingTest(unittest.TestCase):
    """Cover feed boundaries and supported inventory formats."""

    def _inventory(self, data: Any) -> list[kev.InventoryItem]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return kev.parse_inventory_file(path)

    def test_kev_dates_and_fields(self) -> None:
        """Keep inclusive dates, trimmed fields, and input ordering."""
        csv_text = (
            "cveID,dateAdded,vendorProject,product,requiredAction,dueDate,notes\n"
            " CVE-new , 2026-01-31 , Vendor , Product , Patch , Soon , Note \n"
            "CVE-old,2026-01-01,,,,,\n"
            "CVE-before,2025-12-31,,,,,\n"
            "CVE-after,2026-02-01,,,,,\n"
            "CVE-invalid,2026-02-30,,,,,\n"
            "CVE-empty,,,,,,\n"
            ",2026-01-15,,,,,\n"
            "CVE-short,2026-01-15\n"
        )
        self.assertEqual(
            kev.KevSource()._parse(csv_text, 30, dt.date(2026, 1, 31)),
            [
                kev.VulnEntry("CVE-new", "2026-01-31", "Vendor", "Product", "Patch", "Soon", "Note"),
                kev.VulnEntry("CVE-old", "2026-01-01", "", "", "", "", ""),
                kev.VulnEntry("CVE-short", "2026-01-15", "", "", "", "", ""),
            ],
        )

    def test_cyclonedx_inventory(self) -> None:
        """Prefer CycloneDX detection and retain alias ordering and whitespace."""
        self.assertEqual(self._inventory({
            "bomFormat": "CycloneDX", "spdxVersion": "SPDX-2.3",
            "components": [
                {"name": " pkg ", "version": 12, "purl": " pkg:pypi/pkg ", "cpe": "cpe:value"},
                {"name": " ", "version": "ignored"},
                {"name": "bare", "purl": ""},
            ],
        }), [
            kev.InventoryItem("pkg", "12", "cyclonedx:inventory.json", [" pkg:pypi/pkg ", "cpe:value"]),
            kev.InventoryItem("bare", "", "cyclonedx:inventory.json", []),
        ])

    def test_spdx_inventory(self) -> None:
        """Filter invalid external references without stripping valid locators."""
        self.assertEqual(self._inventory({
            "spdxVersion": "SPDX-2.3",
            "packages": [
                {"name": " pkg ", "versionInfo": " 2.0 ", "externalRefs": [
                    None, {}, {"referenceLocator": ""}, {"referenceLocator": " alias "},
                    {"referenceLocator": 123},
                ]},
                {"name": "other", "externalRefs": {"referenceLocator": "ignored"}},
                {"name": " "},
            ],
        }), [
            kev.InventoryItem("pkg", "2.0", "spdx:inventory.json", [" alias ", "123"]),
            kev.InventoryItem("other", "", "spdx:inventory.json", []),
        ])

    def test_generic_inventory(self) -> None:
        """Keep generic conversion rules and explicit blank source values."""
        self.assertEqual(self._inventory([
            None, "ignored", {}, {"name": " "},
            {"name": " pkg ", "version": 3, "source": " local ", "aliases": [" a ", " ", 4, None]},
            {"name": "bare", "aliases": "ignored"},
            {"name": "blank", "source": " "},
        ]), [
            kev.InventoryItem("pkg", "3", "local", ["a", "4", "None"]),
            kev.InventoryItem("bare", "", "file:inventory.json", []),
            kev.InventoryItem("blank", "", "", []),
        ])

    def test_unsupported_and_invalid_inventory(self) -> None:
        """Return no inventory for unsupported or invalid JSON."""
        for data in ({}, {"packages": []}, None, 42):
            with self.subTest(data=data):
                self.assertEqual(self._inventory(data), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(kev.parse_inventory_file(path), [])


class VulnerabilityDetailsTest(unittest.TestCase):
    """Cover branch fixes and recursive NVD configuration traversal."""

    def test_osv_branch_versions(self) -> None:
        """Choose the minimum fix per branch then maximum across branches."""
        affected = {"package": {"name": " pkg ", "ecosystem": " PyPI "}, "ranges": [
            {"events": [{"introduced": "0"}, {"fixed": "1.10"}, {"fixed": "1.2"}, {"fixed": "0"}]},
            {"events": [{"fixed": "2.10"}, {"fixed": "2.2"}, None, {"fixed": ""}]},
            None, {}, {"events": [{"last_affected": "9.0"}]},
        ]}
        self.assertEqual(kev.extract_from_osv({"affected": [
            None, {}, {"package": {"name": " "}}, affected, affected,
            {"package": {"name": "unfixed"}, "ranges": None},
            {"package": {"name": "zero"}, "ranges": [{"events": [{"fixed": "0"}]}]},
        ]}), [
            kev.AffectedSoftware("PyPI:pkg", "PyPI", "2.2", "OSV"),
            kev.AffectedSoftware("unfixed", "", "unknown", "OSV"),
            kev.AffectedSoftware("zero", "", "unknown", "OSV"),
        ])

    def test_nvd_nested_nodes_and_bounds(self) -> None:
        """Preserve depth-first order, bound precedence, and duplicate removal."""
        excluded = {"criteria": "cpe:2.3:a:vendor:pkg:*", "versionEndExcluding": "2.0",
                    "versionEndIncluding": "1.9"}
        included = {"criteria": "cpe:2.3:a:vendor:pkg:*", "versionEndIncluding": "1.9"}
        node = {
            "cpeMatch": [None, excluded, {"criteria": "invalid"},
                         {"criteria": "cpe:2.3:a:vendor:hidden:*", "vulnerable": False}],
            "nodes": [None, {"cpeMatch": [included], "nodes": [{
                "cpeMatch": [excluded, {"criteria": "cpe:2.3:a:vendor:other:*"}],
                "nodes": None,
            }]}],
        }
        payload = {"vulnerabilities": [None, {"cve": None}, {"cve": {
            "configurations": [None, {"nodes": [node]}],
        }}]}
        self.assertEqual(kev.extract_from_nvd(payload), [
            kev.AffectedSoftware("vendor:pkg", "cpe", "2.0", "NVD"),
            kev.AffectedSoftware("vendor:pkg", "cpe", ">1.9", "NVD"),
            kev.AffectedSoftware("vendor:other", "cpe", "unknown", "NVD"),
        ])

    def test_empty_responses(self) -> None:
        """Accept empty responses without inventing affected software."""
        self.assertEqual(kev.extract_from_osv({}), [])
        self.assertEqual(kev.extract_from_nvd({}), [])


class InventoryMatchingTest(unittest.TestCase):
    """Cover normalized exact matches, fuzzy fallback, and output ordering."""

    def test_exact_alias_prevents_fuzzy_fallback(self) -> None:
        """Use exact aliases exclusively when any exact candidate exists."""
        index = kev.build_name_index([
            kev.InventoryItem("local", "1", "pip", ["PyPI:Package"]),
            kev.InventoryItem("package", "2", "dpkg", []),
        ])
        self.assertEqual(kev.match_inventory([
            kev.AffectedSoftware("pypi-package", "", "3", "OSV"),
        ], index), ["local@1 [pip]"])

    def test_fuzzy_threshold_sorting_and_last_source(self) -> None:
        """Keep substring limits, sorted deduplication, and last source wins."""
        index = kev.build_name_index([
            kev.InventoryItem("zlib", "1", "first", ["vendor:zlib"]),
            kev.InventoryItem("zlib", "1", "last", []),
            kev.InventoryItem("alpha-zlib", "2", "apt", []),
            kev.InventoryItem("ssl", "1", "short", []),
        ])
        self.assertEqual(kev.match_inventory([
            kev.AffectedSoftware("zlib-extension", "", "unknown", "NVD"),
            kev.AffectedSoftware("vendor:alpha-zlib", "", "unknown", "NVD"),
            kev.AffectedSoftware("openssl", "", "unknown", "NVD"),
            kev.AffectedSoftware("---", "", "unknown", "NVD"),
        ], index), ["alpha-zlib@2 [apt]", "zlib@1 [last]"])
        self.assertEqual(kev.match_inventory([
            kev.AffectedSoftware("ssl", "", "unknown", "NVD"),
        ], index), ["ssl@1 [short]"])


class MarkdownTest(unittest.TestCase):
    """Verify exact Markdown including blank lines and optional sections."""

    def test_empty_report(self) -> None:
        """Retain the no-results message without a trailing newline."""
        self.assertEqual(kev.render_cve_md([], dt.date(2026, 1, 31), 30, 0, 2),
                         "# KEV Report (2026-01-31)\n\n"
                         "- Window: last 30 days\n- Inventory items: 0\n- KEV rows in window: 2\n"
                         "- Report rows (after inventory filter): 0\n\n"
                         "No matching KEV items found for current filter.")

    def test_full_and_sparse_rows(self) -> None:
        """Retain field order, unescaped text, indentation, and final newline."""
        rows = [
            kev.ReportRow("CVE-1", "2026-01-01", "Vendor", "Product", "Patch *now*",
                          "2026-02-01", "Note", ["pkg@1 [pip]", "other@2 [apt]"], [
                              kev.AffectedSoftware("PyPI:pkg", "PyPI", "2.2", "OSV"),
                              kev.AffectedSoftware("vendor:other", "cpe", ">2", "NVD"),
                          ]),
            kev.ReportRow("CVE-2", "2026-01-02", "V", "P", "Act", "", "", [], []),
        ]
        self.assertEqual(kev.render_cve_md(rows, dt.date(2026, 1, 31), 30, 2, 3),
                         "# KEV Report (2026-01-31)\n\n"
                         "- Window: last 30 days\n- Inventory items: 2\n- KEV rows in window: 3\n"
                         "- Report rows (after inventory filter): 2\n\n"
                         "## CVE-1\n- Date added: 2026-01-01\n- Vendor/Product: Vendor / Product\n"
                         "- Required action: Patch *now*\n- KEV due date: 2026-02-01\n- Notes: Note\n"
                         "- Matched local software:\n  - pkg@1 [pip]\n  - other@2 [apt]\n"
                         "- Affected software and minimum safe version:\n"
                         "  - PyPI:pkg | min_safe_version=2.2 | source=OSV\n"
                         "  - vendor:other | min_safe_version=>2 | source=NVD\n\n"
                         "## CVE-2\n- Date added: 2026-01-02\n- Vendor/Product: V / P\n"
                         "- Required action: Act\n- Matched local software: none\n"
                         "- Affected software and minimum safe version:\n"
                         "  - unknown (no OSV/NVD mapping found)\n")
