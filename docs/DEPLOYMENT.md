# Controlled private deployment

## Supported profile

`compose.yaml` deploys exactly one backend process and one Caddy edge. It is
appropriate for a single owner or a small, controlled evaluation. Caddy serves
the compiled React application, terminates TLS, requires Basic authentication,
and proxies same-origin API requests using a separate internal bearer secret.
The backend is not published to the host.

Do not expose this profile as an anonymous public service. Its sessions,
metrics, and rate limits are process-local, and the shared edge login is not a
user ownership model.

## Prerequisites and secrets

Install a current Docker Engine with Compose v2. Choose a real DNS name and a
host where ports 80/443 reach Caddy. Create ignored secret files:

```bash
mkdir -p deploy/secrets
openssl rand -base64 48 > deploy/secrets/private_access_token
docker run --rm -it caddy:2-alpine caddy hash-password
```

Save only the hash printed by the second command in
`deploy/secrets/web_basic_auth_hash`; do not save the plaintext password in the
repository. Set both files to mode `0600`.

Set deployment values in the invoking shell or an uncommitted `.env`:

```dotenv
MLH_PUBLIC_HOST=movies.example.test
MLH_PUBLIC_ORIGIN=https://movies.example.test
MLH_SITE_ADDRESS=https://movies.example.test
MLH_BASIC_AUTH_USERNAME=movie-helper
```

`MLH_PUBLIC_HOST` is the backend Host allowlist entry.
`MLH_PUBLIC_ORIGIN` is the exact browser origin allowed by CORS.
`MLH_SITE_ADDRESS` tells Caddy which HTTPS site to serve. For real DNS, Caddy
can obtain and renew a public certificate when DNS and ports are correct. A
localhost certificate is suitable only for local evaluation and may require
trusting Caddy's local CA.

## Build, start, and verify

```bash
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --no-log-prefix backend web
curl -u movie-helper:'your-password' https://movies.example.test/health/ready
```

Then sign in through the browser, upload a synthetic/rightfully usable English
SRT, check timing, analyze a scene, and delete the session by replacing it or
calling its DELETE endpoint. Verify an unauthenticated `curl` receives `401`,
the browser/API responses carry the documented security headers, and port 8000
is not reachable from outside the Compose network.

## Provider overlay (still gated)

Do not use this merely because keys exist. Only after ADR-004/ADR-009 and the
privacy/licensing/model gates are accepted, create `openai_api_key` and
`subdl_api_key` secret files and start with:

```bash
docker compose -f compose.yaml -f compose.providers.yaml up -d --build
```

The overlay still requires explicit `MLH_*_ENABLED=true`, risk acknowledgement,
and an exact reviewed OpenAI model. Omit the overlay to guarantee provider-free
operation.

## Updating and rollback

1. Record the current immutable image digests and export `docker compose config`
   as release evidence.
2. Build and scan the candidate images; run the full release checklist.
3. Pull/build the candidate and run `docker compose up -d --no-deps backend web`.
4. Check health, error rate, request latency, login, upload, preview, analysis,
   deletion, and provider fallback (when applicable).
5. On regression, restore the previously recorded image references and repeat
   `up -d`. In-memory sessions are deliberately lost when the backend is
   replaced; users must upload again.

There is no application-data backup. Caddy's volume contains certificate/state
material and is operationally backed up according to the host policy; subtitle
or analysis content must never be added to backups.

## Scaling boundary

Never increase Uvicorn workers or backend replicas with the current session
adapter. Before scaling, implement and verify:

- authenticated session ownership;
- an encrypted shared TTL store with atomic delete/expiry;
- a distributed client/global limiter and analyzer budget;
- shared telemetry with bounded labels; and
- deletion, incident, failover, and disaster-recovery evidence.
