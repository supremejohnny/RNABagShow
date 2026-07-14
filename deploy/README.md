# RNABag persistence test deployment

This stack runs PostgreSQL and private MinIO on loopback-only ports. Mutable
data and secrets stay outside the Git checkout under the deployment root.

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
```

The bootstrap command creates random PostgreSQL, MinIO root, and separate
least-privilege application credentials in the external config file. It
refuses to overwrite an existing file.

Create a runtime-only migration environment outside Git, then initialize the
schema and private bucket:

```bash
DEPLOY_ROOT=/home/johnny/services/rnabag
python3 -m venv "$DEPLOY_ROOT/runtime/persistence-venv"
"$DEPLOY_ROOT/runtime/persistence-venv/bin/pip" install \
  -r "$DEPLOY_ROOT/RNABagShow/backend/requirements-persistence.txt"

set -a
source "$DEPLOY_ROOT/config/persistence.env"
set +a
cd "$DEPLOY_ROOT/RNABagShow"
"$DEPLOY_ROOT/runtime/persistence-venv/bin/python" -m backend.app.migrate
```

For the real backend process, load the same config before starting Uvicorn.
Keep the HTTP service on a trusted/loopback interface until authentication,
TLS, rate limiting, and the public deployment review are complete.

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
`./deploy/persistence-up.sh`, then rerun `python -m backend.app.migrate`.

If deleting through the IDE instead, first stop the backend and run
`./deploy/persistence-down.sh`. Delete the contents of both data directories
together, never only one side and never while a container is running.
