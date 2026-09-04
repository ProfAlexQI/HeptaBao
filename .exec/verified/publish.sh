#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONHASHSEED=0
ROOT="$GITHUB_WORKSPACE"
WORK="$RUNNER_TEMP/heptabao-verified-publication"
EVIDENCE="$RUNNER_TEMP/heptabao-publication-evidence"
BASE=0ce5f152684345b4f553c0519e381e55fa91cbec
EXPECTED=1ad5cee8a2c08a8f2c4091787be3c6530bea5901
BRANCH=exec/v1.9.0-verified-source-transport-v2
mkdir -p "$WORK" "$EVIDENCE"
cp "$ROOT"/.exec/verified/overlay-part-* "$EVIDENCE/"
python "$ROOT/.exec/verified/prepare.py" "$ROOT" "$WORK/prep" 2>&1 | tee "$EVIDENCE/preparation.log"
git worktree add --detach "$WORK/source" "$BASE"
cd "$WORK/source"
git config user.name 'HeptaBao verified source builder'
git config user.email 'heptabao-source-builder@users.noreply.github.com'
python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
{
 python "$WORK/prep/input190/.exec/repair_v1_4_7_source_for_convergence.py"
 python "$WORK/prep/v150/materialize.py" .
 python "$WORK/prep/v160/materialize.py" .
 HEPTABAO_V190_UNMERGED_CONVERGENCE=1 python "$WORK/prep/v170/materialize_v1_7_0.py" . --asset-root "$WORK/prep/v170/assets"
 python "$WORK/prep/v180/materialize.py" .
 cargo +1.98.0 generate-lockfile --offline
 cargo +1.98.0 fmt --all
 python scripts/render_module_source_truth_v1_8_0.py --write
 V190_SOURCE_PARENT="$BASE" python "$WORK/prep/converge.py"
 python "$WORK/prep/augment.py"
 python "$ROOT/.exec/verified/apply_overlay.py" . "$WORK/prep/overlay.b64" 48dbd1b0a7b39cf92c31abb3104ce3c417850d3f4fea788a46f28b9b4538c483
 python scripts/render_module_source_truth_v1_8_0.py --write
 python scripts/render_repository_state_v1_9.py --write
 git add --all
 test "$(git write-tree)" = 5a64d26fbecdef8a33ae759cc7e0fedd7947d695
 python "$ROOT/.exec/verified/finalize_ci.py" .
 git add --all
 test "$(git write-tree)" = "$EXPECTED"
 git diff --cached --check
 git commit -m 'feat(v1.9.0): verified convergence and security regressions; review required'
 test "$(git rev-parse HEAD^{tree})" = "$EXPECTED"
 git bundle create "$EVIDENCE/full-verified-candidate.bundle" HEAD
 python scripts/render_module_source_truth_v1_8_0.py --check
 python scripts/render_repository_state_v1_9.py --check
 python scripts/validate_plan_v1_9_0.py
 python scripts/run_repository_regressions_v1_9.py --output-dir "$EVIDENCE/regressions"
 python -m unittest discover -s tests/platform -p 'test_*.py' -v
 python -m unittest discover -s tests/oracle -p 'test_*.py' -v
 python -m compileall -q scripts tests
 python scripts/build_release_bundle_v1_8.py --output "$EVIDENCE/one.tar.gz"
 python scripts/build_release_bundle_v1_8.py --output "$EVIDENCE/two.tar.gz"
 cmp "$EVIDENCE/one.tar.gz" "$EVIDENCE/two.tar.gz"
 cargo +1.98.0 fmt --all -- --check
 cargo +1.98.0 test --locked --offline --workspace --all-targets
 cargo +1.98.0 clippy --locked --offline --workspace --all-targets -- -D warnings
 test -z "$(git status --porcelain=v1 --untracked-files=all)"
} 2>&1 | tee "$EVIDENCE/full-validation.log"
FULL_COMMIT=$(git rev-parse HEAD)
# This intermediate ref transports non-workflow Git objects only. It is not a
# candidate and deliberately cannot satisfy the source manifest. The connector
# restores the verified workflow tree and verifies EXPECTED before opening a PR.
existing=$(git ls-remote --heads origin "refs/heads/$BRANCH")
test -z "$existing"
git rm -r --quiet .github/workflows
git checkout "$BASE" -- .github/workflows
git add --all
TRANSPORT_TREE=$(git write-tree)
TRANSPORT=$(printf 'chore(transport): transfer verified V1.9 source objects only\n\nNot a product candidate; workflow tree restored to base for transport.\nVerified full tree: %s\nNo qualification or authority.\n' "$EXPECTED" | git commit-tree "$TRANSPORT_TREE" -p "$BASE")
git update-ref refs/heads/verified-source-transport "$TRANSPORT"
git push origin "refs/heads/verified-source-transport:refs/heads/$BRANCH"
export FULL_COMMIT TRANSPORT TRANSPORT_TREE EXPECTED BASE
python - <<'PY'
import json,os,pathlib
value={k.lower():os.environ[k]for k in ('BASE','FULL_COMMIT','EXPECTED','TRANSPORT','TRANSPORT_TREE')}
value.update(schema='heptabao.verified-source-transfer.v1',candidate_published=False,qualification=False,authority_effect='NONE')
pathlib.Path(os.environ['RUNNER_TEMP'],'heptabao-publication-evidence','transfer.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(value,sort_keys=True))
PY
