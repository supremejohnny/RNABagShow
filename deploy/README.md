# RNABag server deployment

The server deployment has two Compose projects:

- `compose.persistence.yml`: PostgreSQL and private MinIO.
- `compose.app-cpu.yml`: one managed FastAPI/Uvicorn process for the frontend,
  API, queue, and CPU inference.

Every service listens on server loopback only. Mutable data and secrets stay
outside the Git checkout under the deployment root. The application mounts the
checkout read-only, so deployment commands cannot modify repository files.

Server layout:

```text
/home/johnny/services/rnabag/
├── RNABagShow/          # deployment-only Git checkout
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
minutes. Later starts reuse the image and are much faster. FastAPI serves both
the canonical frontend and `/api/v1` on port 8000, so a second development
frontend process is not used on the server.

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

This is an internal staging deployment. A later public deployment would put a
TLS reverse proxy on port 443 in front of the same loopback-only FastAPI
service. The current application has no login, so it must not be opened to the
public internet yet.

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
backend first, then run the guarded reset:

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
