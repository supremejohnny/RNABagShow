# RNABag server deployment

The server deployment has three Compose projects and one optional standalone probe:

- `compose.persistence.yml`: PostgreSQL and private MinIO.
- `compose.app-cpu.yml`: one managed FastAPI/Uvicorn process for the frontend,
  API, queue, and CPU inference.
- `compose.app-gpu.yml`: temporary tang3 GPU FastAPI/Uvicorn process using one
  reserved physical GPU exposed as logical `cuda:0`.
- `compose.gateway.yml`: optional Nginx access restricted to the approved
  intranet CIDR. It exposes only the application, never PostgreSQL or MinIO.
- `compose.pong-probe.yml`: standalone Pong connectivity probe for tang3.
  This is a zero-dependency Python HTTP service running on the tailnet. It
  responds to `GET /probe/ping` with `pong\n` and no-store caching. It does
  not perform inference, storage, or authentication. The public-preview bastion
  Nginx proxies only the exact `/probe/ping` path to this service.

FastAPI, PostgreSQL, and MinIO listen on server loopback only. The optional
gateway is the sole intranet listener. Mutable data and secrets stay outside
the Git checkout under the deployment root. The application mounts the
checkout read-only, so deployment commands cannot modify repository files.

Server layout:

```text
/home/johnny/services/rnabag/
├── RNABagShow/          # deployment-only Git checkout (CPU layout)
├── postgres/           # PostgreSQL cluster files
├── object-storage/     # MinIO object data
├── runtime/uploads-tmp/
├── config/             # mode 0700; persistence.env is mode 0600
└── backups/
```

Never edit PostgreSQL or MinIO data files through the IDE while the services
are running. Use SQL tools for PostgreSQL and the MinIO console/S3 API for
objects. The raw directories are only for service-managed storage and full
offline reset/restore operations.

## Prerequisite

The deployment user must be able to run Docker. An administrator can grant it,
then the user must log out and back in:

```bash
sudo usermod -aG docker johnny
```

Verify with `docker info` before continuing.

## First start

Run from the server deployment checkout:

```bash
./deploy/bootstrap-persistence-config.sh
./deploy/persistence-up.sh
./deploy/test-persistence.sh
./deploy/app-up.sh
./deploy/app-smoke-test.sh
```

The bootstrap command creates random PostgreSQL, MinIO root, and separate
least-privilege application credentials in the external config file. It
refuses to overwrite an existing file. `persistence-up.sh` starts the two
services, creates the private bucket and least-privilege MinIO user, then runs
the ordered PostgreSQL migrations in a one-shot container. No host Python
packages or files inside the Git checkout are created.

The first application build downloads the CPU PyTorch wheel and can take a few
minutes. Later starts reuse the image and are much faster. `app-up.sh` always
recreates the application container so that the Uvicorn process loads source
updates from the read-only deployment checkout. FastAPI serves both the
canonical frontend and `/api/v1` on port 8000, so a second development frontend
process is not used on the server.

Run the real PostgreSQL/MinIO round-trip and SHA-256 deduplication tests
independently with:

```bash
./deploy/test-persistence.sh
```

Inspect or stop the application with:

```bash
./deploy/app-status.sh
./deploy/app-down.sh
```

`app-down.sh` stops only FastAPI. PostgreSQL and MinIO continue running. Use
`persistence-down.sh` when those services should also stop.

## Restricted intranet access

FastAPI stays bound to server loopback. Start the separate Nginx gateway only
when teammates need direct intranet access:

```bash
./deploy/gateway-up.sh
```

The first run creates
`/home/johnny/services/rnabag/config/nginx-intranet.conf` with mode `0600`,
validates it with `nginx -t`, starts the gateway, and checks the proxied
readiness endpoint. The current defaults expose
`http://172.16.17.4:8080/` only to the routed VPN client network
`172.28.0.0/24`. The host firewall must independently allow TCP 8080 from the
same source CIDR; `johnny` intentionally does not have authority to change
that system rule.

Inspect or end intranet exposure with:

```bash
./deploy/gateway-status.sh
./deploy/gateway-down.sh
```

`gateway-down.sh` removes only the Nginx gateway container. FastAPI remains on
loopback and PostgreSQL/MinIO keep running. The external Nginx config is
preserved for the next start. Public exposure still requires a separate TLS,
authentication, rate-limit, and network review.

## Temporary tang3 public-IP validation

The user has authorized one temporary end-to-end validation at
`http://101.133.158.8` while domain and ICP readiness are pending. Tang3 keeps
the code checkout on `/mnt/nas/johnny/rnabag/RNABagShow` and all mutable state
under `/home/johnny/services/rnabag/{postgres,object-storage,runtime,backups}`.
The bastion receives only the forwarding-only configuration in
`deploy/public-proxy/`; it must never receive code, checkpoints, uploads,
results, PostgreSQL files, or MinIO objects.

On tang3, first create the external mode-0600 config. The command refuses an
existing file and does not print generated secrets:

```bash
./deploy/bootstrap-tang3-config.sh
RNABAG_CONFIG_FILE=/home/johnny/services/rnabag/config/tang3.env \
  ./deploy/persistence-up.sh
RNABAG_CONFIG_FILE=/home/johnny/services/rnabag/config/tang3.env \
  ./deploy/tang3-up.sh
RNABAG_CONFIG_FILE=/home/johnny/services/rnabag/config/tang3.env \
  ./deploy/tang3-smoke-test.sh
```

The GPU app uses host networking and binds only to the configured tang3
Tailscale address (`100.113.222.1` by default). PostgreSQL and MinIO remain
published only on tang3 loopback. `tang3-status.sh` and `tang3-down.sh` inspect
or stop only the GPU app; stop the GPU app before `persistence-down.sh`.

The bastion install is a separate Nginx operation using
`deploy/public-proxy/nginx-rnabag-public.conf`. It listens on HTTP port 80 for
`_`, `rnabag.com`, and `www.rnabag.com`, forwards frontend and API traffic to
tang3, and has explicit upload, request, connection, and inference timeout
limits. There is no login, TLS, DNS automation, or production claim. Public
exposure remains a resource-abuse and data-handling risk despite the limits.

Rollback order is `tang3-down.sh`, remove/disable the public-proxy Nginx site,
then restore the approved static-only artifact and configuration from
`deploy/public-preview/`. Do not alter `deploy/public-preview/` to implement
the validation proxy.

## Temporary public-IP static preview

The approved bastion preview is static-only and deliberately has no connection
to FastAPI or the main inference server, except for one no-input connectivity
probe. Build its allowlisted files into a new empty temporary directory:

```bash
preview_root="$(mktemp -d)"
./deploy/build-public-preview.sh "$preview_root/site"
```

Deploy only the generated `site/` contents to `/var/www/rnabag` on the bastion
host and install `deploy/public-preview/nginx-rnabag-preview.conf` as an
independent Nginx site. The preview runtime disables upload, demo-data, and run
controls. Nginx permits same-origin browser connections and returns
`503 API_NOT_ENABLED` for `/api/v1/`. Only the exact path `/probe/ping` is
proxied to the tang3 Pong service (currently verified Tailscale address
`100.113.222.1`); this endpoint performs no storage, no inference, and
accepts no input.

The Pong probe is a separate, dependency-free Python HTTP service deployed via
`compose.pong-probe.yml` on tang3. Start it with:

```bash
RNABAG_PONG_BIND_IP=100.113.222.1 RNABAG_PONG_PORT=18080 \
  docker compose -f deploy/compose.pong-probe.yml up -d --build --wait
```

The bind IP `100.113.222.1` is the current verified tang3 Tailscale address and
is runtime state. When validating the pong probe config alongside the env-file
projects, use:

```bash
RNABAG_PONG_BIND_IP=127.0.0.1 \
  docker compose -f deploy/compose.pong-probe.yml config --quiet
```

Do not copy `backend/`, `RNABag/`, `mapping/`, `sampledata/`, credentials, or
mutable server data to the bastion. This temporary HTTP-by-IP preview is not a
substitute for the separate domain, TLS, authentication, abuse-control, and
public-API review.

## Viewing the server page

Keep the HTTP service on loopback until authentication, TLS, rate limiting, and
the public deployment review are complete. From the development computer,
open a tunnel in a terminal:

```bash
ssh -N -L 18000:127.0.0.1:8000 johnny@172.16.17.4
```

Keep that terminal open, then visit `http://127.0.0.1:18000/`. The browser is
showing the frontend served by the server FastAPI process, and uploads go back
through the same tunnel to the server API. Port 18000 is only the local end of
the tunnel; use another unused local port if necessary.

This is an internal staging deployment. A later public deployment would evolve
the gateway to a TLS reverse proxy on port 443 in front of the same
loopback-only FastAPI service. The current application has no login, so the
intranet gateway must not be repurposed as a public listener.

## Inspecting test data

PostgreSQL listens on server loopback port 5432. MinIO's S3 API and console
listen on loopback ports 9000 and 9001. Use an SSH tunnel when connecting an
IDE/browser from another machine. Credentials are in the external
`config/persistence.env`; do not copy them into Git or chat.

Useful SQL:

```sql
SELECT id, task, status, original_filename, file_size_bytes,
       storage_key, created_at, completed_at
FROM analyses
ORDER BY created_at DESC;
```

## Deleting data during testing

Delete one analysis through the API:

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_UUID
```

This leaves a minimal `purged` tombstone row and deletes the original object
only after its last active reference is purged.

To remove the entire test PostgreSQL cluster and every MinIO object, stop the
backend first, then run the guarded reset. The script verifies that the FastAPI
container is stopped and refuses to wipe storage while it is running:

```bash
RNABAG_CONFIRM_RESET=delete-rnabag-test-database-and-objects \
  ./deploy/reset-test-persistence.sh
```

The reset stops PostgreSQL/MinIO and removes only the configured sibling
`postgres/` and `object-storage/` contents. It preserves
`config/persistence.env`. Recreate the empty services with
`./deploy/persistence-up.sh`; that command automatically reruns migrations.

If deleting through the IDE instead, first stop the backend and run
`./deploy/persistence-down.sh`. Delete the contents of both data directories
together, never only one side and never while a container is running.
