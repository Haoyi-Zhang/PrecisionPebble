from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.audit_bibliography import audit, cited_keys, parse_bibtex


class BibliographyAuditTests(unittest.TestCase):
    def test_valid_bibliography(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "main.tex"
            bib = root / "references.bib"
            tex.write_text(r"Evidence~\cite{alpha,beta}.", encoding="utf-8")
            bib.write_text(
                """@article{alpha,
  author = {A. Author},
  title = {Alpha},
  journal = {Journal},
  year = {2020},
  doi = {10.1000/alpha}
}
@book{beta,
  author = {B. Author},
  title = {Beta},
  publisher = {Press},
  year = {2021}
}
""",
                encoding="utf-8",
            )
            report = audit(tex, bib, minimum=2)
            self.assertTrue(report["valid"])
            self.assertEqual(report["entry_count"], 2)
            self.assertEqual(report["cited_key_count"], 2)

    def test_reports_missing_and_unused_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "main.tex"
            bib = root / "references.bib"
            tex.write_text(r"Evidence~\cite{missing}.", encoding="utf-8")
            bib.write_text(
                """@article{unused,
  author = {A. Author},
  title = {Unused},
  journal = {Journal},
  year = {2020},
  doi = {10.1000/unused}
}
""",
                encoding="utf-8",
            )
            report = audit(tex, bib, minimum=1)
            self.assertFalse(report["valid"])
            self.assertEqual(report["missing_citations"], ["missing"])
            self.assertEqual(report["unused_entries"], ["unused"])

    def test_duplicate_doi_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "main.tex"
            bib = root / "references.bib"
            tex.write_text(r"Evidence~\cite{alpha,beta}.", encoding="utf-8")
            bib.write_text(
                """@article{alpha,
  author = {A. Author},
  title = {Alpha},
  journal = {Journal},
  year = {2020},
  doi = {10.1000/SAME}
}
@article{beta,
  author = {B. Author},
  title = {Beta},
  journal = {Journal},
  year = {2021},
  doi = {https://doi.org/10.1000/same}
}
""",
                encoding="utf-8",
            )
            report = audit(tex, bib, minimum=2)
            self.assertFalse(report["valid"])
            self.assertTrue(any("duplicate DOI" in error for error in report["errors"]))

    def test_parser_handles_nested_title_braces_and_optional_cite_argument(self) -> None:
        parsed = parse_bibtex(
            """@inproceedings{key,
  author = {A. Author},
  title = {{I/O} for {DAG}s},
  booktitle = {Proceedings},
  year = {2022},
  url = {https://example.invalid/key}
}
"""
        )
        self.assertEqual(parsed["key"]["fields"]["title"], "{I/O} for {DAG}s")
        self.assertEqual(cited_keys(r"See~\citep[p.~7]{key}."), {"key"})

    def test_verification_ledger_matches_bibliography(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "main.tex"
            bib = root / "references.bib"
            ledger = root / "bibliography-verification.csv"
            tex.write_text(r"Evidence~\cite{alpha}.", encoding="utf-8")
            bib.write_text(
                """@article{alpha,
  author = {A. Author},
  title = {{I/O} Alpha},
  journal = {Journal},
  year = {2020},
  doi = {10.1000/Alpha}
}
""",
                encoding="utf-8",
            )
            ledger.write_text(
                "key,year,title,identifier,manuscript_role,verification_basis,checked_on,status,notes\n"
                "alpha,2020,{I/O} Alpha,https://doi.org/10.1000/alpha,context,official record checked,2026-09-19,retained and cited,\n",
                encoding="utf-8",
            )
            report = audit(tex, bib, minimum=1, verification_path=ledger)
            self.assertTrue(report["valid"])
            self.assertEqual(report["verification_row_count"], 1)

    def test_verification_identifier_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "main.tex"
            bib = root / "references.bib"
            ledger = root / "bibliography-verification.csv"
            tex.write_text(r"Evidence~\cite{alpha}.", encoding="utf-8")
            bib.write_text(
                """@article{alpha,
  author = {A. Author},
  title = {Alpha},
  journal = {Journal},
  year = {2020},
  url = {https://example.org/correct}
}
""",
                encoding="utf-8",
            )
            ledger.write_text(
                "key,year,title,identifier,manuscript_role,verification_basis,checked_on,status,notes\n"
                "alpha,2020,Alpha,https://example.org/wrong,context,official record checked,2026-09-19,retained and cited,\n",
                encoding="utf-8",
            )
            for allow_ledger_identifiers in (False, True):
                report = audit(
                    tex, bib, minimum=1, verification_path=ledger,
                    allow_ledger_identifiers=allow_ledger_identifiers,
                )
                self.assertFalse(report["valid"])
                self.assertTrue(any("identifier" in item for item in report["verification_mismatches"]))

    def test_ledger_identifier_requires_explicit_mode_and_matching_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex, bib, ledger = (root / name for name in ("main.tex", "references.bib", "ledger.csv"))
            tex.write_text(r"Evidence~\cite{alpha}.", encoding="utf-8")
            bib.write_text(
                "@article{alpha, author={A. Author}, title={Alpha}, journal={Journal}, year={2020}}\n",
                encoding="utf-8",
            )
            header = "key,year,title,identifier,manuscript_role,verification_basis,checked_on,status,notes\n"
            row = "alpha,2020,Alpha,https://example.org/alpha,context,primary record and bounded context,2026-09-19,retained and cited,\n"
            ledger.write_text(header + row, encoding="utf-8")
            self.assertFalse(audit(tex, bib, 1, ledger)["valid"])
            report = audit(tex, bib, 1, ledger, allow_ledger_identifiers=True)
            self.assertTrue(report["valid"])
            self.assertEqual(report["ledger_identifier_keys"], ["alpha"])
            self.assertEqual(report["identified_entries"], 1)
            ledger.write_text(header + row.replace("alpha,2020,Alpha,", "alpha,2020,Wrong title,"), encoding="utf-8")
            self.assertFalse(audit(tex, bib, 1, ledger, allow_ledger_identifiers=True)["valid"])

    def test_ledger_identifier_mode_rejects_missing_ledger_and_nonrecord_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex, bib, ledger = (root / name for name in ("main.tex", "references.bib", "ledger.csv"))
            tex.write_text(r"Evidence~\cite{alpha}.", encoding="utf-8")
            bib.write_text(
                "@article{alpha, author={A. Author}, title={Alpha}, journal={Journal}, year={2020}}\n",
                encoding="utf-8",
            )
            self.assertFalse(audit(tex, bib, 1, allow_ledger_identifiers=True)["valid"])
            ledger.write_text(
                "key,year,title,identifier,manuscript_role,verification_basis,checked_on,status,notes\n"
                "alpha,2020,Alpha,unverified-label,context,bounded context,2026-09-19,retained and cited,\n",
                encoding="utf-8",
            )
            self.assertFalse(audit(tex, bib, 1, ledger, allow_ledger_identifiers=True)["valid"])


if __name__ == "__main__":
    unittest.main()
