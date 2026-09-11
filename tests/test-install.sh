#!/usr/bin/env bash
# test-install.sh -- what a submission needs, checked against the tree that is actually shipped.
#
# This is what 0.2.0's `tests/test-install.sh` became (keel-cloud
# `canon/designs/keel-skill-design.md` §8.4). Its static half -- schema version, id charset,
# semver, every `provides` path resolving -- is L1's job in keel-connect-skill
# (`tests/test_dist.py`) and is **not duplicated** here. What survives is the half a submission
# needs and only a built tree can answer: the manifest against the tree beside it, the five
# validator rules of §8.4 step 4, and a real `specify` install.
#
#   ./tests/test-install.sh          static checks against this tree (no network)
#   ./tests/test-install.sh --full   also fetches the download URL and does a real install
#
# Acceptance A-12: **green before the submission issue is filed, not after.** A box ticked that
# was not walked is red.
#
# bash 3.2 compatible (macOS ships it). No GNU-only flags.

set -u
EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FULL=0; [ "${1:-}" = "--full" ] && FULL=1
PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
no()   { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
skip() { printf '  SKIP  %s\n' "$1"; }
head_() { printf '\n== %s\n' "$1"; }

field() {  # field <key> -- the value of a top-level-ish scalar in extension.yml, unquoted
  awk -v k="$1" '$1 == k":" { sub(/^[^:]*:[[:space:]]*/, ""); gsub(/^"|"$/, ""); print; exit }' \
    "$EXT_DIR/extension.yml"
}

head_ "environment"
for t in bash awk sed grep; do
  command -v "$t" >/dev/null 2>&1 && ok "$t present" || no "$t missing"
done
case "$(uname -s)" in
  Darwin) ok "platform: macOS";;
  Linux)  ok "platform: Linux";;
  *)      no "unsupported platform $(uname -s)";;
esac
# 3.9, not 3.11: the floor is Apple's command-line tools, and the whole point of this extension is
# that a founder needs nothing they do not already have (design §4).
if command -v python3 >/dev/null 2>&1; then
  pv="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' \
    && ok "python $pv (>=3.9, the floor this extension declares)" \
    || no "python $pv is below the 3.9 floor"
else
  no "python3 missing -- the one prerequisite"
fi

head_ "the tree this manifest is shipped with"
for f in extension.yml README.md CHANGELOG.md LICENSE SKILL.md; do
  [ -f "$EXT_DIR/$f" ] && ok "$f present" || no "$f missing"
done
for d in commands scripts keel_runtime; do
  [ -d "$EXT_DIR/$d" ] && ok "$d/ present" || no "$d/ missing"
done
[ -f "$EXT_DIR/keel_runtime/__main__.py" ] \
  && ok "the runtime travelled with the extension" \
  || no "keel_runtime/__main__.py missing -- nothing would run"

head_ "every path the manifest names resolves, in this tree"
missing=0
for rel in $(grep -oE 'file: [^,}]*' "$EXT_DIR/extension.yml" | sed -E 's/file:[[:space:]]*//'); do
  if [ -f "$EXT_DIR/$rel" ]; then ok "$rel"; else no "missing $rel"; missing=1; fi
done
[ "$missing" = "0" ] || no "a manifest that names a file it does not ship cannot install"

head_ "the five validator rules (submission guide, step 4)"
ID="$(field id)"
VERSION="$(field version)"
printf '%s' "$ID" | grep -qE '^[a-z][a-z0-9-]*$' \
  && ok "1. id '$ID' is lowercase-with-hyphens" || no "1. id '$ID' must match ^[a-z][a-z0-9-]*$"
printf '%s' "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' \
  && ok "2. version '$VERSION' is bare semver, no leading v" \
  || no "2. version '$VERSION' must be bare semver with no leading v"
# 3. the repository is public and carries extension.yml, README.md and LICENSE **at its root**.
#    Checked here as "this tree is the repository root shape"; that the push happened is step 2's,
#    and the founder's.
if [ -f "$EXT_DIR/extension.yml" ] && [ -f "$EXT_DIR/README.md" ] && [ -f "$EXT_DIR/LICENSE" ]; then
  ok "3. the three files the validator reads are at this tree's root"
else
  no "3. extension.yml, README.md and LICENSE must all be at the repository root"
fi
DOWNLOAD_URL="https://github.com/keeldiscovery/spec-kit-keel/archive/refs/tags/v${VERSION}.zip"
printf '%s' "$DOWNLOAD_URL" \
  | grep -qE '^https://github\.com/[^/]+/[^/]+/(archive/refs/tags/.*\.zip|releases/download/[^/]+/.*\.zip)$' \
  && ok "4. download URL is an accepted shape: $DOWNLOAD_URL" \
  || no "4. download URL is not an accepted shape: $DOWNLOAD_URL"
if [ "$FULL" = "1" ]; then
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -sIL -o /dev/null -w '%{http_code}' "$DOWNLOAD_URL")"
    [ "$code" = "200" ] && ok "4b. download URL is fetchable (HTTP $code)" \
                        || no "4b. download URL answered HTTP $code -- a release must exist at that tag, not merely a tag"
  else
    skip "4b. curl missing -- cannot check the download URL is fetchable"
  fi
else
  skip "4b. download URL fetch (--full)"
fi
printf '  NOTE  5. every checklist box on the submission issue must be true BECAUSE IT WAS DONE.\n'
printf '        A box ticked that was not walked is red, and nobody downstream will catch it.\n'

head_ "commands"
for f in "$EXT_DIR"/commands/*.md; do
  b="$(basename "$f")"
  if head -n1 "$f" | grep -q '^---$' && grep -q '^description:' "$f"; then
    ok "$b has frontmatter with a description"
  else
    no "$b is missing --- frontmatter or a description"
  fi
done
# The namespace rule: ^speckit\.<id>\.<name>$
for name in $(grep -oE 'name: speckit\.[a-z0-9.-]+' "$EXT_DIR/extension.yml" | sed 's/name: //'); do
  printf '%s' "$name" | grep -qE "^speckit\.${ID}\.[a-z0-9-]+$" \
    && ok "command namespaced correctly: $name" \
    || no "command must match ^speckit\\.${ID}\\.[a-z0-9-]+\$: $name"
done
count="$(grep -cE 'name: speckit\.' "$EXT_DIR/extension.yml")"
[ "$count" = "2" ] && ok "two commands, as the submission declares" \
                   || no "the submission declares 2 commands; this manifest has $count"

head_ "no behaviour in a manifest (D6)"
for forbidden in "hooks:" "config:" "templates:" "env:"; do
  if grep -qE "^${forbidden}" "$EXT_DIR/extension.yml"; then
    no "manifest declares '$forbidden' -- a manifest may not change what the script does"
  else
    ok "no '$forbidden' in the manifest"
  fi
done

head_ "the scripts actually answer"
# Against a scratch home, always: this check must never touch a Keel the person running it has
# actually connected, and whatever the connect check starts is stopped again on the next line by
# the script whose whole job that is.
if command -v python3 >/dev/null 2>&1; then
  SCRATCH_HOME="$(mktemp -d 2>/dev/null || mktemp -d -t keelhome)"
  out="$(cd "$EXT_DIR" && python3 scripts/keel_connect_check.py --home "$SCRATCH_HOME" \
          --wait-seconds 0 --no-browser 2>/dev/null | tail -n1)"
  printf '%s' "$out" | grep -q '"outcome"' \
    && ok "keel_connect_check.py printed one line of JSON with an outcome" \
    || no "keel_connect_check.py did not print an outcome: $out"
  out="$(cd "$EXT_DIR" && python3 scripts/keel_disconnect.py --home "$SCRATCH_HOME" \
          2>/dev/null | tail -n1)"
  printf '%s' "$out" | grep -q '"outcome"' \
    && ok "keel_disconnect.py printed one line of JSON with an outcome" \
    || no "keel_disconnect.py did not print an outcome: $out"
  # Belt and braces: a connect launched with a zero wait may not have written its heartbeat yet,
  # so the disconnect above can honestly answer `not_running` while the process is still starting.
  pkill -f "keel_runtime.*$SCRATCH_HOME" >/dev/null 2>&1 || true
  rm -rf "$SCRATCH_HOME"
else
  skip "no python3 -- cannot run the scripts"
fi

head_ "a real install"
if [ "$FULL" = "1" ]; then
  if command -v specify >/dev/null 2>&1; then
    TMP="$(mktemp -d 2>/dev/null || mktemp -d -t keel)"
    # Spec Kit 1.x (measured on 1.0.7.dev0, 2026-09-11): `init` takes `--integration`, not
    # `--ai`, and a local tree installs with `extension add <path> --dev`, not `--from`.
    ( cd "$TMP" && specify init . --here --force --non-interactive --integration claude --ignore-agent-tools >/dev/null 2>&1 \
      && specify extension add "$EXT_DIR" --dev >/dev/null 2>&1 \
      && specify extension list 2>/dev/null | grep -q "$ID" )
    [ $? -eq 0 ] && ok "installed into a scratch Spec Kit project and listed" \
                 || no "a real install failed -- run the commands by hand to see why"
    rm -rf "$TMP"
  else
    skip "specify not installed -- cannot do a real install"
  fi
else
  skip "real install (--full)"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = "0" ] || exit 1
