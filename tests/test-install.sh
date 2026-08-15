#!/usr/bin/env bash
# test-install.sh — verifies the Keel extension is well-formed and installs cleanly.
# Runs on Linux and macOS (bash 3.2 compatible). No GNU-only flags.
#
#   ./tests/test-install.sh          static checks + gate behaviour (no network)
#   ./tests/test-install.sh --full   also does a real `specify` install (needs network)

set -u
EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FULL=0; [ "${1:-}" = "--full" ] && FULL=1
PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
no()   { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
head_() { printf '\n== %s\n' "$1"; }

head_ "environment"
for t in bash git awk sed grep; do
  command -v "$t" >/dev/null 2>&1 && ok "$t present" || no "$t missing"
done
case "$(uname -s)" in Darwin) ok "platform: macOS";; Linux) ok "platform: Linux";; *) no "unsupported platform $(uname -s)";; esac
if command -v python3 >/dev/null 2>&1; then
  pv="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)' \
    && ok "python $pv (>=3.11)" || no "python $pv is below Spec Kit's 3.11 minimum"
else no "python3 missing"; fi
command -v uv >/dev/null 2>&1 && ok "uv present" || printf '  SKIP  uv not installed (needed only for --full)\n'

head_ "manifest"
MAN="$EXT_DIR/extension.yml"
[ -f "$MAN" ] && ok "extension.yml exists" || no "extension.yml missing"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$MAN" <<'PY'
import sys,re
try: import yaml
except ImportError: print("  SKIP  pyyaml not installed, falling back to grep checks"); sys.exit(0)
m=yaml.safe_load(open(sys.argv[1]))
f=0
def ok(s): print("  PASS  "+s)
def no(s):
    global f; f=1; print("  FAIL  "+s)
if m.get("schema_version")=="1.0": ok("schema_version is 1.0")
else: no("schema_version must be '1.0'")
e=m.get("extension",{})
if re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$',e.get("id","")): ok("extension id is lowercase-hyphenated")
else: no("extension id must be lowercase-hyphenated")
if re.match(r'^\d+\.\d+\.\d+$',str(e.get("version",""))): ok("version is semver")
else: no("version must be semver")
if m.get("requires",{}).get("speckit_version"): ok("speckit_version range declared")
else: no("requires.speckit_version missing")
eid=e.get("id")
for c in m.get("provides",{}).get("commands",[]):
    exp="speckit.%s."%eid
    if c["name"].startswith(exp): ok("command namespaced: "+c["name"])
    else: no("command must start with %s: %s"%(exp,c["name"]))
for ev,h in (m.get("hooks") or {}).items():
    if re.match(r'^(before|after)_[a-z]+$',ev): ok("hook event name valid: "+ev)
    else: no("hook event must be before_<cmd> or after_<cmd>: "+ev)
    if not isinstance(h,dict): no("hook value for %s must be a single object, not a list"%ev); continue
    if h.get("command"): ok("hook command declared: %s=%s"%(ev,h.get("command")))
    else: no("hook must declare 'command': %s"%ev)
    if isinstance(h.get("optional"),bool): ok("hook optional flag valid: %s=%s"%(ev,h.get("optional")))
    else: no("hook 'optional' must be a bool: %s"%ev)
    if "condition" in h: no("remove 'condition' from %s - command templates skip hooks that have one"%ev)
if "hooks" in (m.get("provides") or {}): no("hooks must be top-level, not nested under provides:")
sys.exit(f)
PY
  [ $? -eq 0 ] && PASS=$((PASS+1)) || FAIL=$((FAIL+1))
fi

head_ "referenced files exist"
grep -E '^\s+file:' "$MAN" | sed -E 's/.*file:[[:space:]]*"?([^"]*)"?.*/\1/' | while read -r rel; do
  [ -f "$EXT_DIR/$rel" ] && printf '  PASS  %s\n' "$rel" || printf '  FAIL  missing %s\n' "$rel"
done
miss=$(grep -E '^\s+file:' "$MAN" | sed -E 's/.*file:[[:space:]]*"?([^"]*)"?.*/\1/' | while read -r r; do [ -f "$EXT_DIR/$r" ] || echo x; done | wc -l | tr -d ' ')
[ "$miss" = "0" ] && PASS=$((PASS+1)) || FAIL=$((FAIL+1))

head_ "command frontmatter"
for f in "$EXT_DIR"/commands/*.md; do
  b="$(basename "$f")"
  head -n1 "$f" | grep -q '^---$' && grep -q '^description:' "$f" \
    && ok "$b has frontmatter with description" || no "$b missing --- frontmatter or description"
done

head_ "gate script"
G="$EXT_DIR/scripts/bash/keel-gate.sh"
[ -x "$G" ] && ok "keel-gate.sh is executable" || no "keel-gate.sh not executable (chmod +x)"
bash -n "$G" 2>/dev/null && ok "keel-gate.sh parses" || no "keel-gate.sh has a syntax error"

head_ "gate behaviour"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t keel)"
mkdir -p "$TMP/.specify/extensions/keel/scripts/bash" "$TMP/specs"
cp "$G" "$TMP/.specify/extensions/keel/scripts/bash/"
cp "$EXT_DIR/keel-config.template.yml" "$TMP/.specify/extensions/keel/keel-config.yml"
( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "brief blocked with no evidence" || no "brief should have been blocked with no evidence"

mkdir -p "$TMP/keel/evidence"
printf '# Hypothesis\n' > "$TMP/keel/hypothesis.md"
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers reconcile weekly | assumption | high | E-001, E-002, E-003 | open |
EOF
for i in 1 2 3; do printf -- '- participant_role: role%s\n' "$i" > "$TMP/keel/evidence/E-00$i.md"; done
( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "brief blocked while high-risk assumption unvalidated" || no "brief should block on unvalidated high-risk"

sed -i.bak 's/| open |/| validated |/' "$TMP/keel/assumptions.md" 2>/dev/null || \
  sed -i '' 's/| open |/| validated |/' "$TMP/keel/assumptions.md"
( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief >/dev/null 2>&1 )
[ $? -eq 0 ] && ok "brief allowed once assumption validated" || no "brief should pass once validated"

( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh check >/dev/null 2>&1 )
[ $? -eq 0 ] && ok "check passes with hypothesis present" || no "check should pass"

head_ "gate parser robustness"
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers track spend | budget across tools without a single source of truth. | belief | high |  | open |
EOF
( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "brief still blocks when a Statement cell contains a literal '|'" \
  || no "a '|' inside Statement silently bypassed the high-risk gate (regression: see keel-gate.sh unvalidated_high_risk_ids)"

cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Has real evidence behind it. | belief | high | E-001, E-002, E-003 | supported |
| A-002 | Marked supported with no evidence behind it. | belief | high |  | supported |
EOF
( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "brief blocks a high-risk row marked supported/validated with an empty Evidence column" \
  || no "a supported/validated row with zero cited evidence should still block (regression: see keel-gate.sh unbacked_high_risk_ids)"

head_ "guide phase (speckit.keel.guide)"
rm -rf "$TMP/keel"
mkdir -p "$TMP/keel/evidence"

# scenario: totally empty state - guide must still exit 0 and say so plainly
rm -f "$TMP/keel/hypothesis.md" "$TMP/keel/assumptions.md" "$TMP/keel/evidence-plan.md" "$TMP/keel/brief.md" "$TMP/keel/decisions.md"
rm -f "$TMP"/keel/evidence/E-*.md
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide 2>&1 )"
RC=$?
[ $RC -eq 0 ] && ok "guide never blocks on empty state (exit 0)" || no "guide should never block, even with nothing set up yet"
printf '%s\n' "$OUT" | grep -q 'hypothesis: missing' && ok "guide reports missing hypothesis on empty state" \
  || no "guide should report 'hypothesis: missing' on empty state"

# scenario: hypothesis + high-risk assumption, no evidence yet
printf '# Hypothesis\n' > "$TMP/keel/hypothesis.md"
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers reconcile weekly | belief | high |  | open |
EOF
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide 2>&1 )"
RC=$?
[ $RC -eq 0 ] && ok "guide never blocks with hypothesis but no evidence (exit 0)" \
  || no "guide should still exit 0 with hypothesis but no evidence"
printf '%s\n' "$OUT" | grep -q 'brief gate: would currently BLOCK' && ok "guide correctly reports brief gate would BLOCK pre-evidence" \
  || no "guide should report the brief gate would currently BLOCK before any evidence exists"

# scenario: fully passing state (Evidence column populated - an empty one
# would still correctly block per unbacked_high_risk_ids, tested elsewhere)
for i in 1 2 3; do printf -- '- participant_role: role%s\n' "$i" > "$TMP/keel/evidence/E-00$i.md"; done
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers reconcile weekly | belief | high | E-001, E-002, E-003 | validated |
EOF
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide 2>&1 )"
RC=$?
[ $RC -eq 0 ] && ok "guide never blocks on a fully passing state (exit 0)" \
  || no "guide should exit 0 on a fully passing state"
printf '%s\n' "$OUT" | grep -q 'brief gate: would currently PASS' && ok "guide correctly reports brief gate would PASS once thresholds are met" \
  || no "guide should report the brief gate would currently PASS once evidence/roles/validation clear the thresholds"

# scenario: overridden high-risk assumption must not be mislabeled as validated/supported
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers reconcile weekly | belief | high | E-001, E-002, E-003 | validated |
| A-002 | Buyers will pay $20/mo | belief | high |  | open |
EOF
printf 'override: A-002 - accepting pricing risk for v1 pilot\n' > "$TMP/keel/decisions.md"
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide 2>&1 )"
RC=$?
[ $RC -eq 0 ] && ok "guide never blocks with an overridden high-risk assumption (exit 0)" \
  || no "guide should exit 0 with an overridden high-risk assumption"
printf '%s\n' "$OUT" | grep -q '2 high-risk (0 unvalidated-and-blocking)' && \
  ok "guide reports 0 unvalidated-and-blocking once the only unvalidated high-risk row is overridden" || \
  no "guide's high-risk count should drop to 0 unvalidated-and-blocking once the row is overridden (regression: overridden rows must not be reported as validated/supported either - see keel-gate.sh guide phase)"
printf '%s\n' "$OUT" | grep -q 'override recorded in keel/decisions.md for: A-002' && \
  ok "guide surfaces the recorded override by ID" || no "guide should surface which assumption has a recorded override"

head_ "supersession (contradicted high-risk assumption replaced by a new one)"
rm -f "$TMP/keel/decisions.md"
cat > "$TMP/keel/assumptions.md" <<'EOF'
| ID | Statement | Type | Risk | Evidence | Status |
|----|-----------|------|------|----------|--------|
| A-001 | Managers reconcile weekly | belief | high | E-001, E-002, E-003 | validated |
| A-003 | Standup threads alone contain enough signal | belief | high | E-001, E-004 | contradicted |
| A-006 | A useful digest needs input beyond standup threads | belief | high | E-004, E-005 | supported |
EOF
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief 2>&1 )"
RC=$?
[ $RC -ne 0 ] && ok "brief still blocks on a contradicted-but-unresolved high-risk assumption" \
  || no "brief should still block until the contradicted assumption is explicitly resolved (override or superseded)"
printf '%s\n' "$OUT" | grep -q "superseded: A-XXX" && \
  ok "brief's block hint mentions the superseded mechanism, not just override" || \
  no "brief's block hint should mention 'superseded: A-XXX' as a distinct option from override"

printf 'superseded: A-003 - contradicted by E-004/E-005, replaced by A-006\n' > "$TMP/keel/decisions.md"
OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief 2>&1 )"
RC=$?
[ $RC -eq 0 ] && ok "brief passes once the contradicted assumption is recorded as superseded" \
  || no "recording 'superseded: A-003' should unblock brief (regression: see keel-gate.sh superseded_ids/unvalidated_high_risk)"
printf '%s\n' "$OUT" | grep -q 'superseded (contradicted and replaced) recorded in keel/decisions.md for: A-003' && \
  ok "brief surfaces the superseded assumption by ID, distinct from an override" || \
  no "brief should explicitly note which assumption(s) were superseded, separately from overrides"

OUT="$( cd "$TMP" && bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide 2>&1 )"
printf '%s\n' "$OUT" | grep -q 'superseded (contradicted and replaced) recorded in keel/decisions.md for: A-003' && \
  ok "guide phase also surfaces the superseded assumption" || \
  no "guide phase should surface superseded assumptions the same way brief does"

rm -rf "$TMP"

if [ "$FULL" -eq 1 ]; then
  head_ "real install (network)"
  if command -v uvx >/dev/null 2>&1; then
    P="$(mktemp -d 2>/dev/null || mktemp -d -t keelproj)"
    ( cd "$P" && uvx --from git+https://github.com/github/spec-kit.git specify init . --integration claude --force >/dev/null 2>&1 )
    [ -d "$P/.specify" ] && ok "specify init created .specify" || no "specify init failed"
    ( cd "$P" && specify extension add --dev "$EXT_DIR" >/dev/null 2>&1 ) || \
      ( cd "$P" && uvx --from git+https://github.com/github/spec-kit.git specify extension add --dev "$EXT_DIR" >/dev/null 2>&1 )
    [ -d "$P/.specify/extensions/keel" ] && ok "extension installed to .specify/extensions/keel" || no "extension install failed"
    [ -f "$P/.specify/extensions.yml" ] && grep -q 'keel' "$P/.specify/extensions.yml" 2>/dev/null \
      && ok "hooks registered in extensions.yml" || no "hooks not registered"
    if ls "$P"/.claude/commands/*keel* >/dev/null 2>&1 || ls "$P"/.claude/skills/*keel* >/dev/null 2>&1; then
      ok "commands registered for the agent"
    else
      no "commands not registered for the agent"
    fi

    IG="$P/.specify/extensions/keel/scripts/bash/keel-gate.sh"
    [ -x "$IG" ] && ok "gate script installed at the exact path every command's Pre-flight step invokes" \
      || no "keel-gate.sh missing/not executable at .specify/extensions/keel/scripts/bash/ after a real install"
    ( cd "$P" && bash "$IG" init >/dev/null 2>&1 )
    [ $? -eq 0 ] && ok "installed gate script runs successfully from the project root" \
      || no "installed gate script failed to run once actually installed"
    [ ! -e "$P/.specify/extensions/keel/tests" ] && ok ".extensionignore kept tests/ out of the installed copy" \
      || no "tests/ was copied into the installed extension — check .extensionignore"
    [ ! -e "$P/.specify/extensions/keel/.claude" ] && ok ".extensionignore kept .claude/ out of the installed copy" \
      || no ".claude/ was copied into the installed extension — check .extensionignore"
    rm -rf "$P"
  else no "uvx not available; cannot run --full"; fi
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
