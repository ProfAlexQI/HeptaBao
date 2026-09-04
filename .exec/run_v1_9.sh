#!/usr/bin/env bash
set -euo pipefail

BASE_SOURCE_SHA="ca0dd294ca8fa78b61ce4cfb6da0c10011175b83"
CANDIDATE_BRANCH="codex/plan-v1.9.0-full-repository-convergence-v1"
V150_CONTROLLER_SHA="f6c8512d368998a9b0f9998ceede9ff6e3ccd682"
V160_CONTROLLER_SHA="f3165b3d1c4d4c4e8fd923162efd8535dfa09548"
V170_CONTROLLER_SHA="56aea04b4a081c89dd6f5b5ea74da25a2a0d6a8a"
V180_CONTROLLER_SHA="cb2ac86a6cf54d0e8a52f50c817dd7e5accca017"
WORK="${RUNNER_TEMP:?RUNNER_TEMP is required}/v190"
WORKFLOWS="$WORK/workflows"
mkdir -p "$WORK/v150" "$WORK/v160" "$WORK/v170/archive" "$WORK/v180" "$WORKFLOWS"

cat .exec/v1_9_payload/part-* | tr -d '\r\n' | base64 --decode > "$WORK/converge_v1_9.py"
test "$(sha256sum "$WORK/converge_v1_9.py" | awk '{print $1}')" = \
  "7f2cd574e3f31c5363c633074a6db9caf3d1ed5d16e33bac625674d362b79a03"
python -m py_compile "$WORK/converge_v1_9.py"

git fetch --no-tags origin \
  "+refs/heads/exec/v1.5.0-control-plane-materializer-v2:refs/remotes/materializer/v150" \
  "+refs/heads/exec/v1.6.0-runtime-operations-materializer-v2:refs/remotes/materializer/v160" \
  "+refs/heads/exec/v1.7.0-service-materializer-v2:refs/remotes/materializer/v170" \
  "+refs/heads/exec/v1.8.0-operational-service-materializer-v2:refs/remotes/materializer/v180"
test "$(git rev-parse refs/remotes/materializer/v150)" = "$V150_CONTROLLER_SHA"
test "$(git rev-parse refs/remotes/materializer/v160)" = "$V160_CONTROLLER_SHA"
test "$(git rev-parse refs/remotes/materializer/v170)" = "$V170_CONTROLLER_SHA"
test "$(git rev-parse refs/remotes/materializer/v180)" = "$V180_CONTROLLER_SHA"

git show "$V150_CONTROLLER_SHA:.exec/materialize_v1_5_0.py" > "$WORK/v150/materialize.py"
git show "$V150_CONTROLLER_SHA:.exec/patch_v1_5_0.py" > "$WORK/v150/patch.py"
python "$WORK/v150/patch.py" "$WORK/v150/materialize.py"

git show "$V160_CONTROLLER_SHA:.exec/materialize_v1_6_0.py" > "$WORK/v160/materialize.py"
git show "$V160_CONTROLLER_SHA:.exec/patch_v1_6_0.py" > "$WORK/v160/patch.py"
python "$WORK/v160/patch.py" "$WORK/v160/materialize.py"

git archive "$V170_CONTROLLER_SHA" \
  .exec/v1_7_payload .exec/v1_7_assets \
  .exec/patch_v1_7_assets.py .exec/patch_v1_7_assets_v2.py .exec/patch_v1_7_assets_v3.py \
  | tar -xf - -C "$WORK/v170/archive"
cat "$WORK/v170/archive"/.exec/v1_7_payload/materializer-* \
  | base64 --decode | gzip --decompress > "$WORK/v170/materialize.py"
cp -R "$WORK/v170/archive/.exec/v1_7_assets" "$WORK/v170/assets"
python "$WORK/v170/archive/.exec/patch_v1_7_assets.py" "$WORK/v170/assets"
python "$WORK/v170/archive/.exec/patch_v1_7_assets_v2.py" "$WORK/v170/assets"
python "$WORK/v170/archive/.exec/patch_v1_7_assets_v3.py" "$WORK/v170/assets"
for source in "$WORK/v170/assets"/*.rs; do
  rustfmt +1.98.0 --edition 2024 "$source"
done

git show "$V180_CONTROLLER_SHA:.exec/materialize_v1_8_0.py" > "$WORK/v180/materialize.py"
git show "$V180_CONTROLLER_SHA:.exec/patch_v1_8_0.py" > "$WORK/v180/patch.py"
python "$WORK/v180/patch.py" "$WORK/v180/materialize.py"
python -m py_compile \
  "$WORK/v150/materialize.py" "$WORK/v150/patch.py" \
  "$WORK/v160/materialize.py" "$WORK/v160/patch.py" \
  "$WORK/v170/materialize.py" \
  "$WORK/v180/materialize.py" "$WORK/v180/patch.py"

git fetch --no-tags origin "$BASE_SOURCE_SHA"
git switch --detach "$BASE_SOURCE_SHA"
git switch -C "$CANDIDATE_BRANCH"
git config user.name "HeptaBao convergence controller"
git config user.email "heptabao-convergence@users.noreply.github.com"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
python -m pip install --disable-pip-version-check --requirement requirements-plan.txt

python "$WORK/v150/materialize.py" .
test -f .github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml
cp .github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml "$WORKFLOWS/"
python scripts/render_module_source_truth_v1_5_0.py --check
python scripts/validate_plan_v1_5_0.py

python "$WORK/v160/materialize.py" .
test -f .github/workflows/plan-v1.6.0-runtime-recovery-operations.yml
cp .github/workflows/plan-v1.6.0-runtime-recovery-operations.yml "$WORKFLOWS/"
python scripts/render_module_source_truth_v1_6_0.py --check
python scripts/validate_plan_v1_6_0.py

python "$WORK/v170/materialize.py" . --asset-root "$WORK/v170/assets"
test -f .github/workflows/plan-v1.7.0-service-ha-plugin-compatibility.yml
cp .github/workflows/plan-v1.7.0-service-ha-plugin-compatibility.yml "$WORKFLOWS/"
python scripts/render_module_source_truth_v1_7_0.py --check
python scripts/validate_plan_v1_7_0.py

python "$WORK/v180/materialize.py" .
test -f .github/workflows/plan-v1.8.0-operational-service.yml
cp .github/workflows/plan-v1.8.0-operational-service.yml "$WORKFLOWS/"
python scripts/render_module_source_truth_v1_8_0.py --check
python scripts/validate_plan_v1_8_0.py
git diff --check

python scripts/validate_plan_v1_8_0.py
python scripts/validate_plan_v1_7_0.py
python scripts/validate_plan_v1_6_0.py
python scripts/validate_plan_v1_5_0.py
python scripts/validate_plan_v1_4_7.py
python scripts/validate_plan_v1_4_6.py
python scripts/validate_plan_v1_4_5.py
python scripts/validate_module_documentation_v1_4_4.py
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
python -m compileall -q scripts tests
python scripts/build_release_bundle_v1_8.py --output "$WORK/staged-one.tar.gz"
python scripts/build_release_bundle_v1_8.py --output "$WORK/staged-two.tar.gz"
cmp "$WORK/staged-one.tar.gz" "$WORK/staged-two.tar.gz"
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings

mkdir -p planning/generated-workflows
cp "$WORKFLOWS"/*.yml planning/generated-workflows/
V190_SOURCE_PARENT="$BASE_SOURCE_SHA" python "$WORK/converge_v1_9.py"
test -f .github/workflows/plan-v1.9.0-full-repository-convergence.yml
cp .github/workflows/plan-v1.9.0-full-repository-convergence.yml "$WORKFLOWS/"
cp .github/workflows/plan-v1.9.0-full-repository-convergence.yml planning/generated-workflows/
python scripts/validate_plan_v1_9_0.py
python -m unittest discover -s tests/plan -p 'test_plan_v1_9_0.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
python -m compileall -q scripts tests
python scripts/build_release_bundle_v1_8.py --output "$WORK/final-one.tar.gz"
python scripts/build_release_bundle_v1_8.py --output "$WORK/final-two.tar.gz"
cmp "$WORK/final-one.tar.gz" "$WORK/final-two.tar.gz"
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
git diff --check

rm -f \
  .github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml \
  .github/workflows/plan-v1.6.0-runtime-recovery-operations.yml \
  .github/workflows/plan-v1.7.0-service-ha-plugin-compatibility.yml \
  .github/workflows/plan-v1.8.0-operational-service.yml \
  .github/workflows/plan-v1.9.0-full-repository-convergence.yml

git add --all
git commit -m "feat(v1.9.0): converge all repository-controlled source gaps"
candidate_sha="$(git rev-parse HEAD)"
candidate_tree="$(git rev-parse HEAD^{tree})"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
if git ls-remote --exit-code --heads origin "refs/heads/$CANDIDATE_BRANCH" >/dev/null 2>&1; then
  echo "candidate branch already exists; refusing an implicit overwrite" >&2
  exit 1
fi
git push origin "HEAD:refs/heads/$CANDIDATE_BRANCH"
{
  echo '## V1.9.0 convergence source candidate published'
  echo "- commit: \`$candidate_sha\`"
  echo "- tree: \`$candidate_tree\`"
  echo '- workspace crates: 42'
  echo '- repository blockers 059..093: source implemented, review required'
  echo '- external/control blockers: authentic completion required'
  echo '- administrator bypass: false'
  echo '- authority effect: NONE'
} >> "$GITHUB_STEP_SUMMARY"
