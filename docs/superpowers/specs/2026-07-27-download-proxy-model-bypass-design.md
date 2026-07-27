# Download Proxy with Model-Endpoint Bypass

## Goal

Use the configured HTTP(S) proxy for dependency, source, and asset downloads while ensuring that requests to the configured LLM endpoint are made directly.

## Confirmed behavior

On DevBoxS, using the current `.env`:

- A direct Responses API call succeeded.
- The same call forced through `sys-proxy-rd-relay.byted.org:8118` failed with proxy status `403 Forbidden`.
- A call with proxy variables enabled and the exact model hostname in `NO_PROXY` succeeded.

Therefore the model endpoint must bypass the proxy, while other network clients should retain it.

## Minimal design

1. Forward the existing `http_proxy`, `https_proxy`, `HTTP_PROXY`, and `HTTPS_PROXY` values to evaluator agents, verifiers, and meta-agents.
2. Parse the hostname from `OPENAI_BASE_URL` or `OPENAI_API_BASE`.
3. Append that exact hostname to both `no_proxy` and `NO_PROXY`, preserving and deduplicating existing entries.
4. Remove launcher-wide proxy unsets around candidate agent execution. The exact model-host bypass will keep LLM calls direct without disabling proxy access for unrelated downloads.
5. Keep credentials and proxy values out of logs and runtime evidence.

The routing rule is host-scoped:

```text
GitHub / PyPI / uv / task assets -> configured proxy
configured model endpoint       -> direct via NO_PROXY
```

## Scope

The framework change covers Harbor evaluator agents, verifiers, and Harbor meta-agents. Docker daemon image-pull proxy configuration remains a separate host maintenance action because changing daemon networking while experiments are live is unsafe.

No experiment scoring, retry, timeout, dataset, concurrency, or candidate behavior changes are included.

## Error handling

- If no model base URL is configured, preserve the existing proxy and `NO_PROXY` values without inventing a bypass.
- If the base URL has no valid hostname, fail configuration validation rather than silently proxying a model request.
- Preserve user-provided bypass entries and add only the exact model hostname.

## Tests

Add focused tests proving:

- evaluator agent and verifier environments both receive proxy variables;
- meta-agent environments receive proxy variables;
- the model hostname is present in both lowercase and uppercase bypass variables;
- existing bypass entries are preserved without duplication;
- candidate launch commands no longer clear proxy variables globally;
- credentials and proxy values are not emitted in logs.

Run the focused proxy/environment tests, then the full test suite. Deploy only after those checks pass, and update live workspaces at a safe phase boundary without restarting completed generations.
