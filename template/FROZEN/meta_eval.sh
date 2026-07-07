#!/usr/bin/env bash
# FROZEN — self-reference admission gate (Tier 2, lands at M3).
# Contract when wired: for a diff touching operators/, replay K=3 micro-generations
# from the same parent snapshot with old vs new operators (small fixed task subset,
# k=1, budget-capped). New operators must be non-inferior (with margin) to be
# admitted; otherwise the operator part of the diff is reverted
# (ledger: operator_reverted=true) while candidate changes survive.
# The protocol lives here because the thing being evaluated must not own its evaluator.
echo "meta_eval lands at M3 — operator self-modification is not yet admitted" >&2
exit 2
