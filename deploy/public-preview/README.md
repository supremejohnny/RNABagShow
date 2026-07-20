# RNABag public preview

This deployment is a static, API-disabled public preview (with one exception:
the no-input `/probe/ping` endpoint proxied to the tailnet Pong connectivity
probe). It contains only the root redirect page, the two canonical frontend
pages, their shared runtime JavaScript, and the overview image. It must not
contain uploads, sample TSVs, backend code, checkpoints, mapping data,
credentials, or persistence state.

Build into a new empty temporary directory:

```bash
./deploy/build-public-preview.sh /absolute/empty/output-directory
```

The Nginx site serves the release from `/var/www/rnabag`, permits same-origin
browser connections (connect-src `'self'`), returns `503 API_NOT_ENABLED` for
every `/api/v1/` request, and proxies exactly `/probe/ping` to the tailnet Pong
connectivity probe on tang3 (`100.113.222.1`). This single endpoint performs no
storage, no inference, and accepts no input. Port 80 is suitable only for the
approved temporary public-IP preview. Add a domain and TLS before treating it
as a durable public deployment.

To roll back, disable only the `rnabag-preview` Nginx site and reload Nginx.
Do not stop or modify the RNABag services on the main inference server.
