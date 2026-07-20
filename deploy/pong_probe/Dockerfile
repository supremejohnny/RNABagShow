FROM python:3.12-alpine

WORKDIR /app

COPY server.py .

RUN chmod 444 server.py

USER 65534:65534

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=5s \
  CMD python3 -c "import http.client; c=http.client.HTTPConnection('127.0.0.1',8080,timeout=5); c.request('GET','/probe/ping'); r=c.getresponse(); body=r.read(); assert r.status==200, f'unexpected status {r.status}'; assert body==b'pong\n', f'unexpected body {body!r}'; c.close()"

CMD ["python3", "-u", "server.py"]
