from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SIDECAR = WORKFLOWS / "episode-shadow-sidecar.yml"
SMOKE = WORKFLOWS / "episode-shadow-smoke.yml"
UPDATE = WORKFLOWS / "update-and-deploy.yml"
PUBLISH = WORKFLOWS / "publish-committed-data.yml"
RUNNER = ROOT / "scripts" / "run_episode_shadow_sidecar.py"
FETCH_IMERG = ROOT / "scripts" / "fetch_imerg.py"


class EpisodeShadowWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sidecar = SIDECAR.read_text(encoding="utf-8")
        cls.smoke = SMOKE.read_text(encoding="utf-8")
        cls.update = UPDATE.read_text(encoding="utf-8")
        cls.publish = PUBLISH.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.fetch_imerg = FETCH_IMERG.read_text(encoding="utf-8")

    def test_sidecar_has_one_canonical_upstream_and_serialized_writer(self):
        self.assertIn('"IRFEN — Actualizar IMERG y publicar"', self.sidecar)
        self.assertIn('group: "episode-shadow-sidecar"', self.sidecar)
        self.assertIn("cancel-in-progress: false", self.sidecar)
        self.assertEqual(
            self.sidecar.count("python scripts/run_episode_shadow_sidecar.py"),
            1,
        )
        self.assertNotIn("run_episode_shadow_sidecar.py", self.update)
        self.assertNotIn("run_episode_shadow_sidecar.py", self.publish)

    def test_sidecar_permissions_can_persist_and_dispatch_but_not_deploy(self):
        self.assertIn("contents: write", self.sidecar)
        self.assertIn("actions: write", self.sidecar)
        self.assertNotIn("pages: write", self.sidecar)
        self.assertNotIn("id-token: write", self.sidecar)
        self.assertNotIn("actions/deploy-pages", self.sidecar)
        self.assertNotIn("actions/upload-pages-artifact", self.sidecar)

    def test_sidecar_freshness_gate_matches_real_imerg_publication_schema(self):
        self.assertIn(
            "'generated_at':datetime.now(timezone.utc).isoformat()",
            self.fetch_imerg,
        )
        self.assertIn(
            "'source':'NASA GPM IMERG Late Daily'",
            self.fetch_imerg,
        )
        self.assertIn("'product':'GPM_3IMERGDL'", self.fetch_imerg)
        self.assertIn("data['operational_status']='updated'", self.update)
        self.assertIn("data['operational_status']='stale'", self.update)
        self.assertIn("data['last_update_attempt']", self.update)
        self.assertIn(
            "latest.get('source') == 'NASA GPM IMERG Late Daily'",
            self.sidecar,
        )
        self.assertIn("latest.get('product') == 'GPM_3IMERGDL'", self.sidecar)
        self.assertIn("latest['generated_at']", self.sidecar)
        self.assertIn("latest['last_update_attempt']", self.sidecar)
        self.assertIn("status in {'updated','stale'}", self.sidecar)
        self.assertIn("if status == 'updated':", self.sidecar)
        self.assertIn(
            "--dataset-status site/data/latest.json",
            self.sidecar,
        )

    def test_stale_dataset_is_an_explicit_blocked_source_not_a_clear_cycle(self):
        self.assertIn(
            'DATASET_STATUSES = {"updated": "FRESH", "stale": "STALE"}',
            self.runner,
        )
        self.assertIn("sidecar_dataset_freshness_status", self.runner)
        self.assertIn("dataset_freshness_status", self.runner)
        self.assertIn(
            "receipt['dataset_operational_status'] in {'updated','stale'}",
            self.sidecar,
        )
        self.assertIn(
            "receipt['dataset_freshness_status'] in {'FRESH','STALE'}",
            self.sidecar,
        )

    def test_sidecar_persists_only_three_shadow_runtime_files(self):
        expected = (
            "site/data/episodes/shadow/latest.json",
            "site/data/episodes/continuity/shadow/latest.json",
            "site/data/episodes/continuity/shadow/history.json",
        )
        for path in expected:
            self.assertIn(f'"{path}"', self.sidecar)
        self.assertIn('git add -- "${paths[@]}"', self.sidecar)
        self.assertNotIn(
            'site/data/experimental_state.json" "$retry_dir',
            self.sidecar,
        )
        self.assertNotIn(
            'site/data/latest.json" "$retry_dir',
            self.sidecar,
        )
        self.assertNotIn("git push --force", self.sidecar)
        self.assertNotIn("git push -f", self.sidecar)

    def test_main_is_durable_source_and_pages_is_replica(self):
        for marker in (
            "DURABLE_SOURCE_OF_TRUTH",
            "PUBLISHED_REPLICA_ONLY",
            "APPEND_ONLY",
            "automatic_deletion",
            "automatic_tombstones",
        ):
            self.assertIn(marker, self.runner)
        self.assertIn("git fetch --no-tags origin main", self.sidecar)
        self.assertIn("git worktree add --detach", self.sidecar)
        self.assertIn(
            "el estado durable de episodios cambió concurrentemente",
            self.sidecar,
        )

    def test_duplicate_and_out_of_order_sources_cannot_advance_state(self):
        self.assertIn("NOOP_DUPLICATE_SOURCE", self.runner)
        self.assertIn("refuses to rewind or double-count", self.runner)
        self.assertIn("durable sidecar state is partial", self.runner)
        self.assertIn("NOOP_DUPLICATE_SOURCE", self.sidecar)
        self.assertIn(
            "no se crea commit ni se ordena publicación",
            self.sidecar,
        )

    def test_sidecar_never_forwards_to_scientific_gate_or_messages(self):
        self.assertNotIn(
            "evaluate_scientific_episode_gate.py",
            self.sidecar,
        )
        self.assertNotIn("scientific/shadow", self.sidecar)
        self.assertIn(
            "scientific_candidate_forwarding_enabled",
            self.sidecar,
        )
        self.assertIn(
            "receipt['scientific_candidate_forwarding_enabled'] is False",
            self.sidecar,
        )
        self.assertIn("receipt['alerts_created']==0", self.sidecar)
        self.assertIn("receipt['publications_created']==0", self.sidecar)
        self.assertIn("receipt['messages_created']==0", self.sidecar)

    def test_sidecar_dispatches_commit_pinned_existing_publisher_only_after_append(self):
        self.assertIn(
            "if: steps.sidecar.outputs.action == 'APPENDED'",
            self.sidecar,
        )
        self.assertIn(
            "gh workflow run publish-committed-data.yml",
            self.sidecar,
        )
        self.assertIn('-f expected_sha="$PERSISTED_SHA"', self.sidecar)
        self.assertIn('test -n "$PERSISTED_SHA"', self.sidecar)

    def test_published_smoke_requires_exact_main_parity_and_hash_chain(self):
        self.assertIn(
            '"IRFEN - Publicar datos experimentales archivados"',
            self.smoke,
        )
        self.assertEqual(
            self.smoke.count("cmp site/data/episodes/"),
            3,
        )
        self.assertIn(
            "last['potential_output_sha256']==canonical(potential)",
            self.smoke,
        )
        self.assertIn(
            "last['continuity_output_sha256']==canonical(continuity)",
            self.smoke,
        )
        self.assertIn(
            "potential_key==continuity_key==history_key",
            self.smoke,
        )
        self.assertIn(
            "policy['main_role']=='DURABLE_SOURCE_OF_TRUTH'",
            self.smoke,
        )
        self.assertIn(
            "policy['pages_role']=='PUBLISHED_REPLICA_ONLY'",
            self.smoke,
        )

    def test_smoke_preserves_all_non_operational_guards(self):
        for key in (
            "production_use",
            "production_ready",
            "operational_alerting_enabled",
            "public_social_publishing",
            "scientific_candidate_forwarding_enabled",
        ):
            self.assertIn(f"value['{key}'] is False", self.smoke)
        self.assertIn("preview['messages_created']==0", self.smoke)
        self.assertIn("preview['alerts_created']==0", self.smoke)
        self.assertIn("preview['publications_created']==0", self.smoke)
        self.assertIn("preview['email_sent'] is False", self.smoke)


if __name__ == "__main__":
    unittest.main()
