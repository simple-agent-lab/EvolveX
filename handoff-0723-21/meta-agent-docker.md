# Meta-agent Docker/Harbor handoff

- AHE and HyperAgents run the meta-agent through Harbor with Docker image
  `evolve-meta-agent-app:ubuntu-latest`.
- DevBoxS currently has local amd64 image
  `sha256:61b800306be7032671455fe02b60002dad7853ef2e8de1e3e772f91dcb059998`,
  built July 18. It has no repository digest and is absent from the Mac's
  Colima daemon.
- Recent HyperAgents history: the July 22 runs had 20/20 failures caused by an
  incorrect Responses API route/payload, not Docker; the July 23 v11/v12 runs
  had 20/20 successful meta-agent trials using the same image tag.
- AHE debugger failures were missing returned artifacts/submission-contract
  failures, not image startup failures. A LiteLLM price-map timeout was
  non-fatal because it fell back to bundled data.
- The image is not reproducible: it uses `ubuntu:latest`, installs unpinned
  `mini-swe-agent` and Python 3.13, and is only locally tagged. The PR15-expanded
  Dockerfile has not been rebuilt, so it does not describe the existing DevBoxS
  image exactly.

Before the real experiments, choose deliberately between the proven July 18
image and rebuilding the expanded image. In either case, record the exact image
ID; preferably publish a versioned, digest-pinned image after a one-generation
smoke. AEvolve and GEPA do not name this custom image and currently fall back
to Harbor's `ubuntu:latest`.
