# Temporary public application proxy

This is the explicitly temporary HTTP-by-IP validation proxy for the bastion.
Install `nginx-rnabag-public.conf` as the complete Nginx configuration. It
forwards the frontend and `/api/v1/` to the FastAPI process on tang3 at its
currently verified Tailscale address `100.113.222.1:8000`. The proxy is
stateless: do not copy the application checkout, checkpoints, persistence
directories, uploads, or results to the bastion.

The proxy accepts `_`, `rnabag.com`, and `www.rnabag.com`, and keeps a local
`/healthz` response. Request and connection limits are deliberately explicit,
but this deployment has no login, TLS, or durable public-domain routing. It is
not suitable for production or sensitive uploads. Nginx access logging and
request/response buffering are disabled for application traffic, including
temporary-file spill.

Start order:

1. On tang3, start persistence with `tang3.env` and then run `tang3-up.sh`.
2. Run `tang3-smoke-test.sh` using the configured Tailscale bind address.
3. Install this configuration on bastion and reload Nginx.

Rollback is `tang3-down.sh` followed by removal of this site and restoration of
the approved static-only configuration from `deploy/public-preview/`. The
static preview remains API-disabled and must not be modified to provide this
proxy behavior.
