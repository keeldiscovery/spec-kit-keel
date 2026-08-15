#!/usr/bin/env bash
# keel-gate.sh — phase precondition enforcement for the Keel Spec Kit extension.
# Exits 0 when the requested phase may proceed, 1 when it must not.
# POSIX-friendly bash; works on macOS bash 3.2 and Linux bash 4+.

set -u

PHASE="${1:-}"
[ -z "$PHASE" ] && { echo "usage: keel-gate.sh <init|add-evidence|check|brief|guide|plan|implement|audit>" >&2; exit 2; }

find_root() {
  d="$PWD"
  while [ "$d" != "/" ]; do
    [ -d "$d/.specify" ] && { echo "$d"; return 0; }
    d="$(dirname "$d")"
  done
  echo "$PWD"
}

ROOT="$(find_root)"
KEEL="$ROOT/keel"
CFG="$ROOT/.specify/extensions/keel/keel-config.yml"
[ -f "$ROOT/.specify/extensions/keel/keel-config.local.yml" ] && CFG="$ROOT/.specify/extensions/keel/keel-config.local.yml"

cfg() {
  key="$1"; fallback="$2"
  [ -f "$CFG" ] || { echo "$fallback"; return; }
  v="$(grep -E "^[[:space:]]*${key}:" "$CFG" 2>/dev/null | head -n1 | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*(#.*)?$//; s/^"(.*)"$/\1/')"
  [ -n "${v:-}" ] && echo "$v" || echo "$fallback"
}

MIN_EV="$(cfg min_evidence_per_high_risk_assumption 3)"
MIN_SRC="$(cfg min_distinct_sources 2)"
BLOCK="$(cfg block_on_unvalidated_high_risk true)"

FAIL=0
say()  { printf '%s\n' "$*"; }
block(){ say "BLOCKED: $*"; FAIL=1; }
hint() { say "  -> $*"; }

count_evidence() { [ -d "$KEEL/evidence" ] && ls -1 "$KEEL/evidence"/E-*.md 2>/dev/null | wc -l | tr -d ' ' || echo 0; }

distinct_sources() {
  [ -d "$KEEL/evidence" ] || { echo 0; return; }
  grep -h -E '^- participant_role:' "$KEEL/evidence"/E-*.md 2>/dev/null \
    | sed -E 's/^- participant_role:[[:space:]]*//' | sed '/^$/d' | sort -u | wc -l | tr -d ' '
}

# IDs of high-risk rows in assumptions.md that are not validated/supported, one per line.
#
# Columns are read from the RIGHT (Status, then Evidence, then Risk) rather
# than the left. A markdown table row is only unambiguous by position if no
# cell contains a literal '|' - and Statement is free-text prose, so it will
# eventually contain one ("cost | benefit", a pasted table fragment, etc).
# Reading from the right means an embedded pipe in ID/Statement/Type only
# ever shifts fields further left of the ones we actually read, so Risk and
# Status still land correctly. A row that still doesn't parse into the
# expected 6 columns (NF<8) is reported loudly on stderr and skipped, rather
# than silently miscounted - see keel-gate tests for the regression this
# guards against.
unvalidated_high_risk_ids() {
  [ -f "$KEEL/assumptions.md" ] || return 0
  awk -F'|' '
    /^\|/ && $0 !~ /^\|[[:space:]]*-+/ && $0 !~ /\| *ID *\|/ {
      if (NF < 8) {
        line=$0; gsub(/^[ \t]+|[ \t]+$/,"",line)
        print "keel-gate: could not parse assumptions.md row (expected 6 columns): " line > "/dev/stderr"
        next
      }
      id=$2; risk=$(NF-3); status=$(NF-1)
      gsub(/^[ \t]+|[ \t]+$/,"",id); gsub(/^[ \t]+|[ \t]+$/,"",risk); gsub(/^[ \t]+|[ \t]+$/,"",status)
      if (risk=="high" && status!="validated" && status!="supported") print id
    }
  ' "$KEEL/assumptions.md"
}

# IDs of high-risk rows marked supported/validated whose OWN Evidence column
# is completely empty - the row claims real evidence exists behind this
# specific assumption but cites none at all. The project-wide evidence
# count in count_evidence() can't catch that, since it only checks that
# evidence files exist somewhere, not that they're attributed to this
# assumption.
#
# This deliberately does NOT require the Evidence column to independently
# clear $MIN_EV: commands/add-evidence.md asks the agent to use qualitative
# judgment for "supported" ("independent evidence... reasonable
# confidence"), not a hard count matching the project-wide floor - imposing
# that floor per-assumption would re-block ordinary, honestly-judged
# "supported" rows with 1-2 solid pieces of evidence. This only catches the
# unambiguous case: a row claiming supported/validated with zero evidence
# cited. Same right-anchored parsing as unvalidated_high_risk_ids().
unbacked_high_risk_ids() {
  [ -f "$KEEL/assumptions.md" ] || return 0
  awk -F'|' '
    /^\|/ && $0 !~ /^\|[[:space:]]*-+/ && $0 !~ /\| *ID *\|/ {
      if (NF < 8) next
      id=$2; evidence=$(NF-2); risk=$(NF-3); status=$(NF-1)
      gsub(/^[ \t]+|[ \t]+$/,"",id); gsub(/^[ \t]+|[ \t]+$/,"",evidence)
      gsub(/^[ \t]+|[ \t]+$/,"",risk); gsub(/^[ \t]+|[ \t]+$/,"",status)
      if (risk=="high" && (status=="supported" || status=="validated") && evidence=="") print id
    }
  ' "$KEEL/assumptions.md"
}

# IDs with an explicit override recorded in keel/decisions.md, e.g. a line
# containing "override: A-003". These still count as risk for keel.audit to
# surface later; they just don't block the gate.
overridden_ids() {
  [ -f "$KEEL/decisions.md" ] || return 0
  grep -oE 'override:[[:space:]]*A-[0-9]+' "$KEEL/decisions.md" 2>/dev/null \
    | sed -E 's/override:[[:space:]]*//'
}

# Count of unvalidated-or-evidence-thin high-risk assumptions, minus any with a recorded override.
unvalidated_high_risk() {
  all_ids="$( { unvalidated_high_risk_ids; unbacked_high_risk_ids; } | sed '/^$/d' | sort -u)"
  [ -z "$all_ids" ] && { echo 0; return; }
  ov_ids=" $(overridden_ids | tr '\n' ' ') "
  n=0
  for id in $all_ids; do
    case "$ov_ids" in
      *" $id "*) ;;
      *) n=$((n + 1)) ;;
    esac
  done
  echo "$n"
}

# Total number of well-formed assumption rows in assumptions.md, regardless
# of risk or status. Same right-anchored/NF>=8 well-formedness check as the
# functions above, so a row this rejects is also a row those reject.
assumption_count() {
  [ -f "$KEEL/assumptions.md" ] || { echo 0; return; }
  awk -F'|' '
    /^\|/ && $0 !~ /^\|[[:space:]]*-+/ && $0 !~ /\| *ID *\|/ { if (NF >= 8) c++ }
    END { print c+0 }
  ' "$KEEL/assumptions.md"
}

# IDs of every high-risk row, independent of Status - used by the guide
# phase to report "N of M high-risk assumptions cleared" rather than just
# the unvalidated count.
high_risk_ids() {
  [ -f "$KEEL/assumptions.md" ] || return 0
  awk -F'|' '
    /^\|/ && $0 !~ /^\|[[:space:]]*-+/ && $0 !~ /\| *ID *\|/ {
      if (NF < 8) next
      id=$2; risk=$(NF-3)
      gsub(/^[ \t]+|[ \t]+$/,"",id); gsub(/^[ \t]+|[ \t]+$/,"",risk)
      if (risk=="high") print id
    }
  ' "$KEEL/assumptions.md"
}

high_risk_count() { high_risk_ids | sed '/^$/d' | wc -l | tr -d ' '; }

open_contradictions() {
  [ -f "$KEEL/assumptions.md" ] || { echo 0; return; }
  # grep -c always prints a count, even 0, but exits 1 on zero matches —
  # capture once so that exit code never triggers a second, duplicate echo.
  n="$(grep -c 'contradicted' "$KEEL/assumptions.md" 2>/dev/null)"
  echo "${n:-0}"
}

active_spec() {
  br="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  [ -n "$br" ] && [ -f "$ROOT/specs/$br/spec.md" ] && { echo "$ROOT/specs/$br/spec.md"; return; }
  ls -1 "$ROOT"/specs/*/spec.md 2>/dev/null | head -n1
}

case "$PHASE" in
  init)
    [ -f "$KEEL/hypothesis.md" ] && {
      say "NOTE: keel/hypothesis.md already exists. Re-running init will rewrite it."
      say "      Existing assumption IDs must be preserved."
    }
    ;;

  add-evidence|check)
    [ -f "$KEEL/hypothesis.md" ] || { block "keel/hypothesis.md not found."; hint "Run /speckit.keel.init first."; }
    [ -f "$KEEL/assumptions.md" ] || { block "keel/assumptions.md not found."; hint "Run /speckit.keel.init first."; }
    ;;

  brief)
    [ -f "$KEEL/assumptions.md" ] || { block "No assumptions recorded."; hint "Run /speckit.keel.init."; }
    ev="$(count_evidence)"; src="$(distinct_sources)"; con="$(open_contradictions)"
    ov_list="$(overridden_ids | tr '\n' ' ')"
    unbacked_list="$(unbacked_high_risk_ids | tr '\n' ' ')"
    uhr="$(unvalidated_high_risk)"
    say "evidence files: $ev   distinct participant roles: $src   unvalidated high-risk: $uhr   contradictions: $con"
    [ -n "$ov_list" ] && say "NOTE: override recorded in keel/decisions.md for: $ov_list (excluded from the count above, still surfaced by keel.audit)."
    [ -n "$unbacked_list" ] && say "NOTE: marked supported/validated with an empty Evidence column: $unbacked_list (counted as unvalidated above)."
    [ "$ev" -lt "$MIN_EV" ] && { block "only $ev evidence files, minimum is $MIN_EV."; hint "Run /speckit.keel.add-evidence after more interviews."; }
    [ "$src" -lt "$MIN_SRC" ] && { block "only $src distinct participant roles, minimum is $MIN_SRC."; hint "One person's opinion is not a segment."; }
    if [ "$BLOCK" = "true" ] && [ "$uhr" -gt 0 ]; then
      block "$uhr high-risk assumption(s) still unvalidated."
      hint "Validate them, downgrade the risk with a reason, or add a line containing 'override: A-XXX' to keel/decisions.md."
      hint "To disable this gate project-wide: set block_on_unvalidated_high_risk: false in keel-config.local.yml (recorded in the audit)."
    fi
    [ "$con" -gt 0 ] && say "WARNING: $con open contradiction(s). These must appear in the brief's unvalidated risks."
    ;;

  guide)
    # Never blocks - guide is a read-only status/routing phase for
    # /speckit.keel.guide. It reports the same underlying numbers `brief`
    # would gate on, so the command can route the user without
    # re-implementing this arithmetic in prose.
    hyp="missing"; [ -f "$KEEL/hypothesis.md" ] && hyp="present"
    ep="missing"; [ -f "$KEEL/evidence-plan.md" ] && ep="present"
    br="missing"; [ -f "$KEEL/brief.md" ] && br="present"
    ac="$(assumption_count)"; hrc="$(high_risk_count)"; uhr="$(unvalidated_high_risk)"
    ev="$(count_evidence)"; src="$(distinct_sources)"; con="$(open_contradictions)"
    ov_list="$(overridden_ids | tr '\n' ' ')"

    say "hypothesis: $hyp"
    say "evidence plan: $ep"
    say "assumptions: $ac total, $hrc high-risk ($uhr unvalidated-and-blocking)"
    say "evidence: $ev files across $src distinct participant roles"
    say "contradictions: $con open"
    say "brief: $br"
    [ -n "$ov_list" ] && say "NOTE: override recorded in keel/decisions.md for: $ov_list."

    if [ "$ev" -ge "$MIN_EV" ] && [ "$src" -ge "$MIN_SRC" ] && { [ "$BLOCK" != "true" ] || [ "$uhr" -eq 0 ]; }; then
      say "brief gate: would currently PASS"
    else
      reasons=""
      [ "$ev" -lt "$MIN_EV" ] && reasons="$reasons only $ev evidence files (need $MIN_EV);"
      [ "$src" -lt "$MIN_SRC" ] && reasons="$reasons only $src distinct roles (need $MIN_SRC);"
      [ "$BLOCK" = "true" ] && [ "$uhr" -gt 0 ] && reasons="$reasons $uhr unvalidated high-risk assumption(s);"
      say "brief gate: would currently BLOCK -$reasons"
    fi
    ;;

  plan)
    if [ -d "$KEEL" ]; then
      [ -f "$KEEL/brief.md" ] || { block "keel/ exists but keel/brief.md does not."; hint "Run /speckit.keel.brief before planning."; }
      s="$(active_spec)"
      if [ -n "${s:-}" ] && [ -f "$KEEL/brief.md" ]; then
        grep -q 'keel:' "$s" 2>/dev/null || say "WARNING: no keel traceability markers in $s. Round-trip audit will fall back to text matching."
      fi
    fi
    ;;

  implement)
    s="$(active_spec)"
    [ -n "${s:-}" ] || { block "no spec.md found."; hint "Run /speckit.specify first."; }
    if [ -d "$KEEL" ]; then
      uhr="$(unvalidated_high_risk)"
      [ "$uhr" -gt 0 ] && say "WARNING: building on $uhr unvalidated high-risk assumption(s). keel.audit will flag any that are load-bearing."
    fi
    ;;

  audit)
    s="$(active_spec)"
    if [ -z "${s:-}" ]; then
      block "no spec.md found."
      hint "Run /speckit.specify first — audit needs a spec to score, with or without keel/."
    elif [ -d "$KEEL" ] && [ -f "$KEEL/brief.md" ]; then
      say "keel/brief.md present — audit will diff the build against evidence, not just score the spec."
    else
      say "NOTE: no keel/brief.md found; audit runs in spec-quality-only mode (no evidence to diff the build against)."
    fi
    ;;

  *) say "unknown phase: $PHASE" >&2; exit 2 ;;
esac

[ "$FAIL" -eq 0 ] && say "keel-gate: $PHASE OK"
exit "$FAIL"
