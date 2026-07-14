# RNABagShow Agent Guide

This file is the durable handoff for future coding agents working in this
repository. Read it before changing preprocessing, inference, API behavior, or
the frontend. If a local `harness/` directory exists, read its notes as well;
that directory is intentionally ignored by Git and may contain newer local run
state.

## Product stage

RNABagShow is currently a research-use paper showcase for biology,
computational-biology, and medical-domain experts. It is no longer a static
mock: the frontend uploads an expression TSV to FastAPI and the backend runs
the copied RNABag PyTorch checkpoints. The first PostgreSQL plus private
S3-compatible object-storage persistence phase is approved and follows the
design in `harness/database/analysis-storage-schema.md` when that local file is
available. Public exposure, public TLS/domain routing, application
authentication, and SSO remain separate deployment decisions. A restricted
Nginx reverse-proxy gateway bound to `172.16.17.4:8080` and allowlisting
`172.16.17.0/24` is approved for the current intranet test phase only.

Never describe model output as a clinical diagnosis. Persistence is limited to
the approved analysis metadata/result and private raw-upload object described
by the persistence design. Do not add analytics or log uploaded expression
data. Do not broaden retention, access, or secondary-use behavior without
explicit approval.

## Server deployment checkout

The server checkout at
`/home/johnny/services/rnabag/RNABagShow` is deployment-only. Never edit,
generate, format, patch, commit, or otherwise modify repository files in that
checkout. Source changes must be made and committed in the development
workspace, then delivered to the server only with `git fetch` / `git pull`.
After updating the checkout, only read-only inspection and explicit deployment
commands may run there.

All mutable server state lives outside the Git checkout under its sibling
directories:

- `/home/johnny/services/rnabag/postgres/`
- `/home/johnny/services/rnabag/object-storage/`
- `/home/johnny/services/rnabag/runtime/`
- `/home/johnny/services/rnabag/config/` (mode `0700`, owned by `johnny`)
- `/home/johnny/services/rnabag/backups/`

Do not place database files, object data, runtime uploads, logs, generated
secrets, or environment files in the repository checkout.

## Canonical components

- `frontend/index.html`: canonical, self-contained showcase frontend.
- `frontend/ranbag_lab.html`: iframe entry for the expanded task workspace.
- `backend/app/main.py`: FastAPI app, raw upload streaming, in-memory jobs,
  persistent/in-memory job routing, single-worker queue, temporary-file
  cleanup, and static-file serving.
- `backend/app/persistence.py`: PostgreSQL migrations and analysis state,
  private S3-compatible object operations, SHA-256 object reuse, recovery, and
  purge/reference handling.
- `backend/migrations/`: ordered PostgreSQL schema migrations.
- `deploy/`: persistence, CPU application, and restricted intranet gateway
  Compose stacks, external-config bootstrap, server smoke checks, and guarded
  test-data reset commands.
- `backend/app/inference.py`: TSV validation, GeneID mapping, ordered 4096-HVG
  matrix construction, checkpoint loading, and prediction formatting.
- `backend/app/catalog.py`: API task names, modalities, and label order.
- `RNABag/data/process_data.py`: offline preprocessing reference.
- `RNABag/data/tcga_hvg_gene_4096.txt`: canonical ordered model genes.
- `mapping/Human_GRCh38.p13_annot.tsv`: canonical GRCh38.p13 mapping.
- `RNABag/infer_code/checkpoints/`: copied model checkpoints.
- `RNABag/data/README.md` and `backend/README.md`: preprocessing and runtime
  contracts that must remain synchronized with code.

The root `index.html` is only a redirect to `frontend/index.html`. Do not revive
the removed/older frontend entry as a second source of truth.

## Confirmed preprocessing contract

1. Input is UTF-8 TSV: first column `GeneID`, remaining columns samples.
2. A short export title may precede the actual header within the first five
   rows.
3. GeneID is unrounded ASCII integer text. Never guess rounded identifiers.
4. Preserve input order. For duplicate GeneIDs or multiple GeneIDs mapping to
   one model name, keep the first occurrence and discard later rows.
5. Prefer the mapping's current `Symbol`. Use a historical `Synonyms` value only
   when it is the row's sole HVG candidate and no other GeneID owns that name as
   a current Symbol or synonym.
6. Reindex to the exact 4096-HVG order, fill absent genes with zero, then apply
   `log1p`.
7. `raw_sum` and `input_sum` intentionally contain the same sum of the final
   log1p vector. Both summary-token positions are required by the checkpoints
   for the team's batch-effect mitigation contract.

The synonym rule is a recommended showcase rule, not a training-derived gold
standard. Do not change it or encode expected biological predictions until the
team supplies and approves a golden dataset.

## Tasks and inference

Enabled API tasks:

- `tissue_cancer_detection`
- `tissue_origin_identification`
- `platelet_cancer_detection`
- `platelet_tumor_localization`

Plasma remains disabled even though a checkpoint file is present. Platelet
cancer detection uses the legacy Healthy-probability threshold `0.003955459`;
other tasks use argmax. Label order in `backend/app/catalog.py` must continue to
match `RNABag/infer_code/data/id_to_name.py` and checkpoint training.

The service defaults to one inference worker. This is intentional: expected
early concurrency is 5-10 visitors, while the company's eight GPUs are also
used for SwanLab training. On the future server, reserve a GPU through
`CUDA_VISIBLE_DEVICES`/`RNABAG_DEVICE` rather than allowing showcase inference
to contend with every training device.

## Local verification

From the repository root, start both local processes in one terminal:

```bash
./run.sh
```

Open `http://127.0.0.1:5173/`. `run.sh` serves the project frontend on port 5173
and FastAPI on port 8000; one `Ctrl+C` stops both child processes. The frontend
also supports other local Live Server and `file://` origins by routing the API
to port 8000; CORS is restricted to local origins.

`run.sh` is development-only. On the server, use the Compose commands described
in `deploy/README.md`; FastAPI serves both the frontend and API from one
loopback-only port, and the deployment checkout is mounted read-only.

Before handing off backend/preprocessing changes, run:

```bash
python3 -m py_compile backend/app/main.py backend/app/inference.py
python3 -m unittest discover -s backend/tests -v
sed -n '/<script>/,/<\/script>/p' frontend/index.html | sed '1d;$d' | node --check
bash -n deploy/*.sh
docker compose --env-file deploy/persistence.env.example \
  -f deploy/compose.persistence.yml config --quiet
RNABAG_UID="$(id -u)" RNABAG_GID="$(id -g)" \
  docker compose --env-file deploy/persistence.env.example \
  -f deploy/compose.app-cpu.yml config --quiet
RNABAG_GATEWAY_CONFIG_FILE=/tmp/rnabag-nginx-intranet.conf \
  docker compose --env-file deploy/persistence.env.example \
  -f deploy/compose.gateway.yml config --quiet
```

Keep unrelated user changes in a dirty worktree. Do not normalize or rewrite
the real sample TSVs merely to silence line-ending or trailing-whitespace Git
warnings.

## Data and privacy

The showcase still has no login. In memory-only mode, uploads stay temporary
and are deleted after success, failure, cancellation, or shutdown. In approved
persistent mode, original bytes are retained only in the private object bucket
and analysis metadata/result JSON only in PostgreSQL; processing copies remain
temporary and must be deleted on every terminal path. Do not store PHI in
logs, tests, `harness/`, Git, or deployment documentation. Credentials live
only in the external mode-0600 config file; never copy them into repository
files.
