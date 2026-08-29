#!/usr/bin/env python3
"""Compatibility entry point for :mod:`critics.run_critics`.

The implementation lives beside the critic packet assembler so the self-service
workflow and this legacy command cannot drift apart.
"""
from critics.run_critics import call_model, chunked_review, main, tally_verdict

__all__ = ["call_model", "chunked_review", "main", "tally_verdict"]


if __name__ == "__main__":
    raise SystemExit(main())
