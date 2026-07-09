# MetaAgent

This is the live Harbor recipe for memory-oriented evolution on MiniSWE. It
keeps the newest-parent selector and markdown-focused mutable surface while
switching the meta-agent operator to `agent_command` and evaluation to Harbor on
`swe-bench-lite`.

`surface.include` exposes `target/**` and `operators/*.md`.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`select: {variant: newest}` resolves to [`library/select/newest.py`](../../library/select/newest.py).
