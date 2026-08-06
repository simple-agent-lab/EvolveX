# Host-Optional Proxy Routing Design

## Goal

Keep optional proxy support for users who need it without encoding proxy policy in built-in experiment recipes or evaluation identity.

## Scope

- Remove `evaluator.runtime.proxy` declarations from all built-in recipes.
- Preserve the existing runtime proxy schema for backward compatibility and custom configurations, including `mode: required`.
- When no proxy policy is declared, inherit explicitly supplied standard proxy variables as optional host transport.
- Continue adding the configured model endpoint hostname to `NO_PROXY`/`no_proxy` so model calls bypass dependency-download proxies.
- Persist only redacted routing evidence; never persist proxy values.
- Leave evaluation-contract and runtime-consistency schemas unchanged.

## Behavior

Strict runtime environment resolution follows this order:

1. If `evaluator.runtime.proxy` is present, retain its existing optional/required behavior.
2. If it is absent and no standard proxy variable is supplied, forward no proxy variables.
3. If it is absent and `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` is supplied, forward the consistent upper/lower-case aliases to the agent, verifier, and meta-agent roles as host-inherited optional transport.
4. When any proxy is active, merge the model endpoint hostname into both `NO_PROXY` aliases.
5. Reject conflicting upper/lower-case proxy alias values as before.

Existing initialized workspaces containing explicit proxy policy remain valid. New workspaces generated from built-in recipes do not include proxy policy in `runtime.json` or its digest.

## Evidence and Security

Runtime evidence records whether host proxy routing was active and which environment-variable names were forwarded. It does not record proxy URLs, credentials, endpoint URLs, or authentication paths. Proxy activation remains transport evidence rather than a benchmark-comparability field.

## Testing

- A strict runtime with no proxy declaration and no proxy environment forwards nothing.
- A strict runtime with no proxy declaration inherits supplied standard proxy aliases and bypasses the model endpoint.
- Explicit optional and required proxy policies preserve their existing behavior.
- Conflicting proxy aliases remain rejected.
- Recipe conformance verifies built-in recipes no longer declare proxy policy while generated runtime configuration remains valid.

## Non-goals

- No new runtime module or host-profile format.
- No evaluation-contract, archive, or receipt schema changes.
- No stronger host/container identity comparison.
- No proxy auto-discovery beyond explicitly supplied standard environment variables.
