# RNABag local backend

The local API currently provides a deterministic mock inference adapter so the
upload, validation, task queue, polling, cleanup, and frontend result flow can
be developed before the production preprocessing contract is frozen.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.app.main:app --reload --port 8000
```

Then open `http://127.0.0.1:8000/`.

The mock adapter never calls an RNABag checkpoint. Raw uploads are written to a
temporary directory and removed after validation and mock inference complete.
The API streams request bodies to disk instead of loading an entire upload into
Python memory. One worker processes analyses in order; up to ten waiting jobs
are accepted by default. This intentionally keeps local concurrency predictable
before GPU inference is introduced.

The upload endpoint accepts the TSV as the raw HTTP request body:

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v1/analyses?task=platelet_cancer_detection' \
  -H 'Content-Type: text/tab-separated-values' \
  -H 'X-RNABag-Filename: Platelet_sample_to_joh.tsv' \
  --data-binary @sampledata/Platelet_sample_to_joh.tsv
```

Environment variables:

- `RNABAG_MAX_UPLOAD_BYTES`: upload limit, default 2 GiB.
- `RNABAG_QUEUE_CAPACITY`: queued analyses, default 10.
- `RNABAG_RESULT_TTL_SECONDS`: in-memory result lifetime, default 3600 seconds.
- `RNABAG_TEMP_DIR`: optional temporary upload directory.
