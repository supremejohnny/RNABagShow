# RNABag local backend

The local FastAPI service accepts an expression TSV, applies the repository's
GeneID/Symbol mapping and ordered 4096-HVG preprocessing, and runs the selected
RNABag checkpoint with PyTorch.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
./run.sh
```

Open `http://127.0.0.1:5173/`. The script serves the frontend on port 5173 and
FastAPI on port 8000 in the same terminal; `Ctrl+C` stops both. The first
request for each task also loads and caches that task's checkpoint, so it is
slower than later requests.

## Request flow and concurrency

Uploads stream to a temporary file rather than being buffered entirely in the
web process. One worker processes analyses in order and caches one model per
used task. This prevents 5-10 simultaneous visitors from launching overlapping
GPU jobs or loading duplicate checkpoint copies. Up to ten waiting analyses are
accepted by default; excess requests receive HTTP 429.

The service has two explicit modes:

- Default memory mode keeps job metadata/results in memory for one hour and
  deletes each raw upload after inference.
- `RNABAG_PERSISTENCE_ENABLED=true` stores analysis metadata/results in
  PostgreSQL and original bytes in a private S3-compatible bucket. The worker
  downloads a temporary processing copy and deletes that copy after success,
  failure, cancellation, or shutdown.

Persistent startup applies ordered migrations, verifies the private bucket,
and returns interrupted `validating`/`running` rows to `queued`. The API never
returns the storage bucket or key. There is still no login, so this test-stage
service must remain bound to trusted/local interfaces.

The upload endpoint accepts the TSV as the raw HTTP request body:

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v1/analyses?task=platelet_cancer_detection' \
  -H 'Content-Type: text/tab-separated-values' \
  -H 'X-RNABag-Filename: Platelet_sample_to_joh.tsv' \
  --data-binary @sampledata/Platelet_sample_to_joh.tsv
```

Poll `/api/v1/analyses/{analysis_id}` until it succeeds, then read
`/api/v1/analyses/{analysis_id}/result`.

Every sample column after `GeneID` is an independent model input. A TSV with
`N` sample columns therefore returns exactly `N` entries in `predictions`, in
the original column order, and every entry carries the corresponding
`sample_id`. The frontend renders all returned sample predictions in a
scrollable result list.

The frontend's one-click demo reads the two verified, versioned fixtures from
`sampledata/` through `GET /api/v1/demo-data/tissue` or
`GET /api/v1/demo-data/platelet`, then submits the selected bytes through the
same analysis endpoint as a user upload. The demo source files are read-only
application assets; they are not maintained as mutable MinIO objects.

## Configuration

- `RNABAG_MAX_UPLOAD_BYTES`: upload limit; default 2 GiB.
- `RNABAG_QUEUE_CAPACITY`: waiting analyses; default 10.
- `RNABAG_RESULT_TTL_SECONDS`: in-memory result lifetime; default 3600 seconds.
- `RNABAG_TEMP_DIR`: optional temporary upload directory.
- `RNABAG_PERSISTENCE_ENABLED`: enable PostgreSQL + S3 persistence when `true`.
- `RNABAG_DATABASE_URL`: PostgreSQL connection URL.
- `RNABAG_S3_ENDPOINT_URL`: S3-compatible endpoint, such as local MinIO.
- `RNABAG_S3_ACCESS_KEY` / `RNABAG_S3_SECRET_KEY`: application credentials;
  do not use the MinIO root credentials.
- `RNABAG_S3_BUCKET`: private raw-input bucket.
- `RNABAG_S3_REGION`: S3 region; default `us-east-1`.
- `RNABAG_DEVICE`: `auto` (CUDA when available, otherwise CPU), `cpu`, `cuda`,
  `cuda:N`, or `mps`.
- `RNABAG_BATCH_SIZE`: inference batch size; default 8 on CUDA and 1 elsewhere.

For the future shared training server, reserve one inference GPU with
`CUDA_VISIBLE_DEVICES=<gpu-id>` before starting the service and keep SwanLab
training jobs on the other devices. The initial single-worker policy should be
changed only after measuring model memory and latency on that server.

## Preprocessing contract

- The actual `GeneID` header may be the first row or may follow a short export
  title within the first five rows.
- GeneID matching is exact; identifiers must not be rounded.
- Duplicate GeneIDs and model Symbols use **first occurrence wins**.
- Current Symbols take priority. A historical HVG synonym is used only when it
  is the row's sole HVG synonym and no other GeneID owns that name.
- Missing genes are zero-filled in the exact 4096-HVG order, then `log1p` is
  applied.
- `raw_sum` and `input_sum` are intentionally identical sums of the final
  log1p vector and occupy the two summary-token positions expected by the
  checkpoints.

The synonym rule is the current recommended showcase policy and must be
revisited with the team's future golden dataset. See `RNABag/data/README.md`.

Plasma remains disabled even though a copied checkpoint exists; its public
workflow will be enabled only after its input/sample contract is reviewed.

## Persistent data contract

`backend/migrations/001_create_analyses.sql` creates the first-stage
`analyses` table. `result` and `input_summary` are JSONB objects; original TSV
bytes are never stored in PostgreSQL. Every result includes
`schema_version: 1`.

Object keys use `uploads/{first-content-analysis-id}/input.tsv`. The service
hashes raw bytes with SHA-256 while streaming. Repeated identical uploads get
independent analysis rows but reuse the first active object under a
transaction-scoped advisory lock. Filenames are display metadata only.

`DELETE /api/v1/analyses/{id}` marks the row `purged`, removes result/error
payloads, and deletes the physical object only when no unpurged analysis still
references it. A full test-environment reset is documented in
`deploy/README.md`.
