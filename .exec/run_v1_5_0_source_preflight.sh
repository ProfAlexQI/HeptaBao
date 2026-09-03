#!/usr/bin/env bash
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

EXPECTED_HEAD=8752e2797d3939b3d0f824ac4728f7b498707612
EXPECTED_BASE=54d524214df443752a2ecaeff6d4a05625bf52c7
export CARGO_TARGET_DIR="$RUNNER_TEMP/heptabao-v150-source-preflight-target"

cp .exec/materialize_v1_5_0.py "$RUNNER_TEMP/materialize_v1_5_0.py"
cp .exec/patch_v1_5_0.py "$RUNNER_TEMP/patch_v1_5_0.py"
python "$RUNNER_TEMP/patch_v1_5_0.py" "$RUNNER_TEMP/materialize_v1_5_0.py"
python -m py_compile \
  "$RUNNER_TEMP/materialize_v1_5_0.py" \
  "$RUNNER_TEMP/patch_v1_5_0.py"

gh api "repos/$GITHUB_REPOSITORY/pulls/63" > "$RUNNER_TEMP/pr63.json"
test "$(jq -r .state "$RUNNER_TEMP/pr63.json")" = open
test "$(jq -r .draft "$RUNNER_TEMP/pr63.json")" = false
test "$(jq -r .base.ref "$RUNNER_TEMP/pr63.json")" = integration/v1.4.4-technical-candidate
test "$(jq -r .head.ref "$RUNNER_TEMP/pr63.json")" = codex/plan-v1.4.7-post-merge-truth-and-external-admission-v1
test "$(jq -r .base.sha "$RUNNER_TEMP/pr63.json")" = "$EXPECTED_BASE"
test "$(jq -r .head.sha "$RUNNER_TEMP/pr63.json")" = "$EXPECTED_HEAD"
merge_sha="$(jq -r .merge_commit_sha "$RUNNER_TEMP/pr63.json")"
test "$merge_sha" != null
test "$(gh api "repos/$GITHUB_REPOSITORY/commits/$merge_sha" --jq .commit.verification.verified)" = true

git fetch --no-tags origin "$EXPECTED_BASE" "$EXPECTED_HEAD" "$merge_sha"
read -r observed parent_one parent_two extra <<<"$(git rev-list --parents -n 1 "$merge_sha")"
test "$observed" = "$merge_sha"
test "$parent_one" = "$EXPECTED_BASE"
test "$parent_two" = "$EXPECTED_HEAD"
test -z "${extra:-}"
test "$(git rev-parse "$merge_sha^{tree}")" = "$(git rev-parse "$EXPECTED_HEAD^{tree}")"

git switch --detach "$merge_sha"
git switch -C tmp/v1.5.0-prospective-source-preflight
test -z "$(git status --porcelain=v1 --untracked-files=all)"
printf 'pr=63\nbase=%s\nhead=%s\nprospective_merge=%s\ntree=%s\n' \
  "$EXPECTED_BASE" "$EXPECTED_HEAD" "$merge_sha" "$(git rev-parse HEAD^{tree})"

python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
python "$RUNNER_TEMP/materialize_v1_5_0.py" .
python scripts/render_module_source_truth_v1_5_0.py --check
python scripts/validate_plan_v1_5_0.py
python scripts/validate_plan_v1_4_7.py
python scripts/validate_plan_v1_4_6.py
python scripts/validate_plan_v1_4_5.py
python scripts/validate_module_documentation_v1_4_4.py
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
python -m compileall -q scripts tests
git diff --check

rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
rustc +1.98.0 --version --verbose
cargo +1.98.0 --version --verbose
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings

test ! -e .exec
test -f .github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml
grep -R "authority_effect: NONE" \
  planning/HEPTABAO_*V1_5_0*.yaml \
  planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml
! grep -R \
  "production_authority: true\|release_authority: true\|migration_authority: true\|compatibility_claim: true\|qualification: true" \
  planning/HEPTABAO_*V1_5_0*.yaml \
  planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml

{
  echo '## V1.5.0 prospective source preflight'
  echo
  echo '- source: current PR #63 GitHub prospective merge'
  echo '- workspace crates: 28'
  echo '- publication: NONE'
  echo '- merge authority: NONE'
  echo '- external/control blocker effect: NONE'
} >> "$GITHUB_STEP_SUMMARY"
