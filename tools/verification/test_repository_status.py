"""Current-state projections must not promote stale, partial or unrelated proof."""
from copy import deepcopy
import unittest
from unittest.mock import Mock
from tools.verification.repository_status import GitHubReader, ReadError, collect, markdown, project

A = "a" * 40
B = "b" * 40


def fixture():
    runs = [dict(id=i, path=f".github/workflows/{name}.yml", head_sha=A, head_branch="main", event="push",
                 status="completed", conclusion="success", html_url="https://github.com/owner/repo/actions/runs/" + str(i))
            for i, name in enumerate(("ci", "package"), 1)]
    raw = {"started_at": "2026-10-03T00:00:00+00:00", "finished_at": "2026-10-03T00:00:01+00:00", "errors": [],
           "repository": {"id": 1, "full_name": "owner/repo", "default_branch": "main"},
           "main_before": {"commit": {"sha": A}, "protected": False}, "main_after": {"commit": {"sha": A}},
           "branches": {"items": [dict(name="lane/" + lane, commit={"sha": A}) for lane in ("verify", "heal", "expand", "evolve")], "complete": True},
           "runs": {"items": runs, "complete": True}}
    raw.update({name: {"items": [], "complete": True} for name in ("pulls", "issues", "releases", "rulesets")})
    return raw


class RepositoryStatusTests(unittest.TestCase):
    def test_current_proof_is_scoped_not_conformance(self):
        report = project(fixture(), {"git_sha": A})
        self.assertTrue(report["selected_post_merge_workflows_pass"])
        self.assertTrue(report["lanes_synchronized"])
        self.assertTrue(report["source_metadata"]["matches_observed_main"])
        for key in ("repository_conformance", "retirement_authorized", "release_authorized"):
            self.assertFalse(report[key])
        self.assertFalse(report["enforcement"]["approved_requirements_verified"])

    def test_main_change_invalidates_current_head_claim(self):
        raw = fixture(); raw["main_after"]["commit"]["sha"] = B
        report = project(raw, {"git_sha": A})
        self.assertFalse(report["collection_complete"])
        self.assertFalse(report["selected_post_merge_workflows_pass"])
        self.assertIsNone(report["lanes_synchronized"])

    def test_partial_branches_cannot_claim_synchronized(self):
        raw = fixture(); raw["branches"]["complete"] = False
        self.assertIsNone(project(raw, {})["lanes_synchronized"])

    def test_missing_lane_is_not_equal(self):
        raw = fixture(); raw["branches"]["items"].pop()
        self.assertFalse(project(raw, {})["lanes_synchronized"])

    def test_older_success_does_not_mask_newer_failure(self):
        raw = fixture(); failed = deepcopy(raw["runs"]["items"][0]); failed.update(id=3, conclusion="failure")
        raw["runs"]["items"].append(failed)
        self.assertFalse(project(raw, {})["selected_post_merge_workflows_pass"])

    def test_pr_success_is_not_post_merge_proof(self):
        raw = fixture(); raw["runs"]["items"][0]["event"] = "pull_request"
        self.assertFalse(project(raw, {})["selected_post_merge_workflows_pass"])

    def test_wrong_head_or_branch_cannot_supply_proof(self):
        for key, value in (("head_sha", B), ("head_branch", "work/other")):
            with self.subTest(key=key):
                raw = fixture(); raw["runs"]["items"][0][key] = value
                self.assertFalse(project(raw, {})["selected_post_merge_workflows_pass"])

    def test_missing_or_incomplete_runs_cannot_pass(self):
        raw = fixture(); raw["runs"]["items"] = []
        self.assertFalse(project(raw, {})["selected_post_merge_workflows_pass"])
        raw = fixture(); raw["runs"]["complete"] = False
        self.assertFalse(project(raw, {})["selected_post_merge_workflows_pass"])

    def test_empty_scope_is_not_vacuously_green(self):
        with self.assertRaises(ValueError):
            project(fixture(), {}, ())

    def test_issues_exclude_pull_requests_and_preserve_incomplete_flag(self):
        raw = fixture(); raw["issues"] = {"items": [{"number": 12, "title": "custody"}, {"number": 19, "pull_request": {}}], "complete": False}
        report = project(raw, {})
        self.assertEqual([item["number"] for item in report["issues"]["items"]], [12])
        self.assertFalse(report["issues"]["complete"])

    def test_source_metadata_is_bound_to_its_own_revision(self):
        self.assertFalse(project(fixture(), {"git_sha": B})["source_metadata"]["matches_observed_main"])

    def test_pagination_preserves_partial_results_on_failure(self):
        reader = GitHubReader("owner/repo")
        reader.get = Mock(side_effect=[([{"id": 1}], {"Link": '<ignored>; rel="next"'}), ReadError("http:403")])
        result = reader.pages("/branches")
        self.assertFalse(result["complete"])
        self.assertEqual(result["items"], [{"id": 1}])
        self.assertEqual(result["error"], "http:403")

    def test_pagination_bound_does_not_claim_completion(self):
        reader = GitHubReader("owner/repo")
        reader.get = Mock(return_value=([{"id": 1}], {"Link": '<ignored>; rel="next"'}))
        self.assertFalse(reader.pages("/branches", max_pages=1)["complete"])

    def test_collection_checks_immutable_repository_identity(self):
        reader = GitHubReader("owner/repo")
        reader.get = Mock(return_value=({"id": 2, "default_branch": "main"}, {}))
        with self.assertRaisesRegex(ReadError, "identity-unverified"):
            collect(reader, 1)

    def test_reader_rejects_foreign_or_traversing_endpoints(self):
        reader = GitHubReader("owner/repo", "not-a-real-token")
        for path in ("https://other.example", "/../secrets", "/branches?token=x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reader.get(path)

    def test_markdown_does_not_fabricate_empty_collection(self):
        raw = fixture(); raw["pulls"]["complete"] = False
        text = markdown(project(raw, {}))
        self.assertIn("absence is authoritative only for a complete collection", text)
        self.assertIn("Collection complete: `False`", text)


if __name__ == "__main__":
    unittest.main()
