"""Positive, negative, preservation, and current-repository profile checks."""
from __future__ import annotations

from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from tools.verification.verify_repository_profile import (
    ProfileError, check_repository, derive, main, regular_file, safe_path, semver,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "src/simvltanea/layout.toml"


class RepositoryProfileTests(unittest.TestCase):
    def setUp(self):
        self.document = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
        self.profile = self.document["repository_profile"]

    def rejected(self, code):
        with self.assertRaisesRegex(ProfileError, code):
            derive(self.document)

    def test_registered_derivations(self):
        report = derive(self.document)
        self.assertEqual(report["classified_roles"], 22)
        self.assertEqual({item["canonical_path"] for item in report["objects"]}, {
            "tools/verification/verify_repository_profile.py",
            "tests/governance/test_repository_profile.py",
            "docs/governance/REPOSITORY_PROFILE.md",
        })

    def test_draft_never_claims_conformance(self):
        report = derive(self.document)
        self.assertEqual(report["state"], "draft")
        self.assertEqual(report["claim"], "derivation-preview-only")
        self.assertFalse(report["repository_conformance"])

    def test_repeatable_output(self):
        self.assertEqual(derive(self.document), derive(deepcopy(self.document)))

    def test_mapping_order_does_not_change_output(self):
        reordered = json.loads(json.dumps(self.document, sort_keys=True))
        self.assertEqual(derive(reordered), derive(self.document))

    def test_logical_role_relocation_changes_only_projection(self):
        old = derive(self.document)["objects"]
        self.document["paths"]["tools"] = "operations"
        new = derive(self.document)["objects"]
        self.assertEqual([item["id"] for item in old], [item["id"] for item in new])
        self.assertIn("operations/verification/verify_repository_profile.py",
                      [item["canonical_path"] for item in new])

    def test_concept_term_drives_filename_not_identity(self):
        old = derive(self.document)["objects"]
        self.profile["concepts"]["repository-profile"]["term"] = "maintenance-contract"
        new = derive(self.document)["objects"]
        self.assertEqual([item["id"] for item in old], [item["id"] for item in new])
        self.assertTrue(all("maintenance_contract" in item["canonical_path"].lower() for item in new))

    def test_keywords_never_drive_names(self):
        old = derive(self.document)["objects"]
        self.profile["objects"][0]["keywords"] = ["arbitrary discovery phrase"]
        self.assertEqual(old, derive(self.document)["objects"])

    def test_missing_profile(self):
        del self.document["repository_profile"]
        self.rejected("profile.fields")

    def test_unknown_profile_field(self):
        self.profile["implicit_approval"] = True
        self.rejected("profile.fields")

    def test_unknown_schema(self):
        self.profile["schema"] = "simvltanea.repository-profile/v2"
        self.rejected("profile.unsupported-schema")

    def test_invalid_versions(self):
        for value in ("01.0.0", "1.0", "1.0.0-01", "1.0.0+", "1.0.0-", "v1.0.0", "1.0.0\n", "", 1, None):
            with self.subTest(value=value):
                self.assertFalse(semver(value))

    def test_valid_versions(self):
        for value in ("1.0.0", "0.1.0", "1.0.0-draft.1", "1.0.0-rc.1+build.001", "1.0.0-x-y-z.--"):
            with self.subTest(value=value):
                self.assertTrue(semver(value))

    def test_wrong_version_type(self):
        self.profile["version"] = 1
        self.rejected("profile.invalid-version")

    def test_future_profile_is_not_silently_accepted(self):
        self.profile["version"] = "2.0.0"
        self.rejected("profile.unsupported-version")

    def test_future_vocabulary_is_not_silently_accepted(self):
        self.profile["vocabulary_version"] = "2.0.0"
        self.rejected("profile.unsupported-version")

    def test_bad_state_type(self):
        self.profile["state"] = []
        self.rejected("profile.invalid-state")

    def test_state_is_not_approval(self):
        self.profile["state"] = "effective"
        self.rejected("profile.activation-not-supported")
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["--enforce"]), 2)
        self.assertIn("activation.requires-owner-approved-successor", error.getvalue())

    def test_unregistered_concept(self):
        self.profile["objects"][0]["concept"] = "guessed"
        self.rejected("object.unregistered-fact")

    def test_unregistered_class(self):
        self.profile["objects"][0]["class"] = "guessed"
        self.rejected("object.unregistered-fact")

    def test_duplicate_identity(self):
        self.profile["objects"][1]["id"] = self.profile["objects"][0]["id"]
        self.rejected("object.duplicate-identity")

    def test_duplicate_canonical_path(self):
        extra = deepcopy(self.profile["objects"][0])
        extra["id"] = "simvltanea.other"
        self.profile["objects"].append(extra)
        self.rejected("object.canonical-path-collision")

    def test_case_only_role_collision(self):
        self.document["paths"]["tools"] = "DOCS"
        self.rejected("layout.case-or-unicode-collision")

    def test_unicode_normalization_collision(self):
        self.document["paths"]["tools"] = "caf\u00e9"
        self.document["paths"]["tests"] = "cafe\u0301"
        self.rejected("layout.case-or-unicode-collision")

    def test_authority_conflict(self):
        self.profile["authorities"]["naming"]["conflict"] = "unresolved"
        self.rejected("authority.unresolved-conflict")

    def test_duplicate_fact_authority(self):
        self.profile["authorities"]["other"] = deepcopy(self.profile["authorities"]["naming"])
        self.rejected("authority.duplicate-fact")

    def test_missing_owner(self):
        self.profile["owner_authority"] = "nobody"
        self.rejected("profile.missing-owner")

    def test_unpinned_authority(self):
        self.profile["authorities"]["naming"]["git_blob"] = "main"
        self.rejected("authority.unpinned-input")

    def test_missing_role_classification(self):
        del self.profile["role_metadata"]["archive"]
        self.rejected("roles.incomplete-classification")

    def test_unknown_material(self):
        self.profile["role_metadata"]["archive"]["material"] = "misc"
        self.rejected("roles.unknown-material")

    def test_protected_material_cannot_be_normalized(self):
        self.profile["classes"]["verification-command"]["role"] = "archive"
        self.rejected("class.protected-material")

    def test_dangling_relationship(self):
        self.profile["objects"][1]["relationships"] = {"tests": ["missing"]}
        self.rejected("object.dangling-or-self-reference")

    def test_self_relationship(self):
        obj = self.profile["objects"][1]
        obj["relationships"] = {"tests": [obj["id"]]}
        self.rejected("object.dangling-or-self-reference")

    def test_wrong_relationship_type(self):
        self.profile["objects"][0]["relationships"] = {"tests": [self.profile["objects"][1]["id"]]}
        self.rejected("object.relationship-type-mismatch")

    def test_unknown_relationship(self):
        self.profile["objects"][1]["relationships"] = {"depends-on-maybe": ["missing"]}
        self.rejected("object.invalid-relationship")

    def test_private_object_is_not_projected(self):
        self.profile["objects"][0]["access"] = "private"
        self.rejected("object.not-public-active")

    def test_unknown_keyword_field_does_not_become_authority(self):
        self.profile["objects"][0]["tags"] = ["rename-me"]
        self.rejected("object.fields")

    def test_missing_exception_review(self):
        self.profile["exceptions"][0]["review_when"] = ""
        self.rejected("exception.missing-review-condition")

    def test_duplicate_exception(self):
        self.profile["exceptions"].append(deepcopy(self.profile["exceptions"][0]))
        self.rejected("exception.duplicate-scope")

    def test_cannot_target_preserved_subtree(self):
        self.document["paths"]["tools"] = "archive/operations"
        self.rejected("object.in-preserved-scope")

    def test_invalid_relative_paths(self):
        for value in ("../x", "/x", "x/../y", "x//y", "x\\y", "x/./y", ".", "", "x\ny", "x.", "x ", "nul.txt", "COM1.py", "x:y", "x" * 241):
            with self.subTest(value=value), self.assertRaises(ProfileError):
                safe_path(value)

    def test_unsafe_formatter_in_locator(self):
        self.profile["authorities"]["naming"]["locator"] = "{config.__class__}/lint.yml"
        self.rejected("locator.must-use-logical-role")

    def test_unknown_locator_role(self):
        self.profile["authorities"]["naming"]["locator"] = "{unknown}/lint.yml"
        self.rejected("locator.unknown-role")

    def test_regular_file_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "file").write_text("safe")
            (root / "alias").symlink_to(root / "file")
            with self.assertRaises(ProfileError):
                regular_file(root, "alias")
            self.assertEqual(regular_file(root, "file"), root / "file")

    def test_regular_file_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            root = Path(tmp)
            (Path(other) / "file").write_text("outside")
            (root / "escape").symlink_to(other, target_is_directory=True)
            with self.assertRaisesRegex(ProfileError, "filesystem.symlink-escape"):
                regular_file(root, "escape/file")

    def test_unavailable_context_has_stable_exit_and_no_private_path(self):
        error = io.StringIO()
        with patch.dict("sys.modules", {"tools.paths": None}), redirect_stderr(error):
            self.assertEqual(main(["--root", "private-intake-example"]), 2)
        self.assertNotIn("private-intake-example", error.getvalue())
        self.assertIn("no changes made", error.getvalue())

    def test_legacy_contract_is_not_reversioned(self):
        self.assertEqual(self.document["contract"], {"version": "0.1.0"})

    @unittest.skipUnless((ROOT / ".git").exists(), "requires a complete Git checkout, not a source reconstruction")
    def test_current_repository_registered_objects_and_pins(self):
        from tools.paths import load_layout
        report = check_repository(self.document, ROOT, load_layout(ROOT))
        # Shadow observation only: draft pin drift must not become a blocking gate.
        self.assertIsInstance(report["errors"], list)
        self.assertFalse(report["repository_conformance"])
        print("DRAFT PROFILE SHADOW REPORT " + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
