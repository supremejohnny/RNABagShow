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

## Request flow and local concurrency

Uploads stream to a temporary file rather than being buffered entirely in the
web process. One worker processes analyses in order and caches one model per
used task. This prevents 5-10 simultaneous visitors from launching overlapping
GPU jobs or loading duplicate checkpoint copies. Up to ten waiting analyses are
accepted by default; excess requests receive HTTP 429.

Raw uploads are deleted as soon as validation/inference finishes (including
failures and cancellation). Job metadata and results live only in memory and
expire after one hour by default. There is no login or persistent result store
in this local showcase phase.

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

## Configuration

- `RNABAG_MAX_UPLOAD_BYTES`: upload limit; default 2 GiB.
- `RNABAG_QUEUE_CAPACITY`: waiting analyses; default 10.
- `RNABAG_RESULT_TTL_SECONDS`: in-memory result lifetime; default 3600 seconds.
- `RNABAG_TEMP_DIR`: optional temporary upload directory.
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
