"""Keep the canonical climate mirror in the same commit as its event input."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/imerg-early-probe.yml'


class ClimateMirrorSyncTests(unittest.TestCase):
    def test_canonical_mirror_is_rebuilt_before_worktree_commit(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        start = text.index('              cd "$worktree" || exit 1')
        end = text.index('              git config user.name', start)
        block = text[start:end]
        expected = [
            'archive_imerg_early_probe.py',
            'build_phase2_event_reanalysis.py',
            'build_phase2_climate_evidence.py',
            'validate_phase2_climate_evidence.py',
            'build_phase2_subunit_rainfall_evidence.py',
            'validate_phase2_subunit_rainfall_evidence.py',
        ]
        offsets = []
        for name in expected:
            command = f'python scripts/{name} || exit 1'
            self.assertIn(command, block)
            offsets.append(block.index(command))
        self.assertEqual(offsets, sorted(offsets))
        staged = text[text.index('              git add', end):text.index('              if git diff', end)]
        self.assertIn('site/data/phase2/event_reanalysis.json', staged)
        self.assertIn('site/data/phase2/climate_evidence_normalized_v0_1.json', staged)

    def test_validator_failure_cannot_reach_persistence_in_and_subshell(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        start = text.index('              cd "$worktree" || exit 1')
        end = text.index('              git config user.name', start)
        block = text[start:end]
        # Execute the actual workflow command block with non-network test doubles.
        shell = '''
        set -euo pipefail
        worktree=.
        python() {
          case "$1" in
            scripts/validate_phase2_climate_evidence.py) return 1 ;;
            *) return 0 ;;
          esac
        }
        (
        ''' + block + '''
        echo MUST_NOT_PERSIST
        ) && echo MUST_NOT_PUBLISH
        '''
        result = subprocess.run(['bash','-c',shell], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('MUST_NOT', result.stdout)


if __name__ == '__main__':
    unittest.main()
