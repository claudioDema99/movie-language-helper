# Dependency Review

## Purpose

Phase 1 introduces the project's first third-party runtime and development
dependencies. Both package ecosystems use committed lockfiles, and installation
and CI use frozen/locked modes. Repeat this review whenever a direct dependency
is added or materially upgraded.

## Locked inventory

After `make bootstrap`, inspect the complete resolved dependency trees:

```bash
make dependency-inventory
```

The backend source of truth is `backend/uv.lock`; the frontend source of truth
is `frontend/package-lock.json`. Review unexpected transitive dependencies,
native extensions, abandoned packages, and duplicate major versions before
accepting a lockfile change.

## Licenses and SBOMs

Review the installed backend metadata and the frontend lockfile license fields:

```bash
make dependency-licenses
```

Generate CycloneDX SBOMs for both packages:

```bash
make dependency-sbom
```

The ignored `.artifacts/` directory receives the reports. The current uv
CycloneDX exporter does not include Python license metadata, which is why the
separate installed-metadata report above is required. Review each component's
declared license and flag missing, unknown, copyleft, or project-incompatible
licenses for a deliberate decision before release. Generated reports are review
artifacts rather than repository source of truth, so they are not committed.

## Vulnerabilities

Run the ecosystem vulnerability checks while online:

```bash
make dependency-audit
```

`uv audit` is currently a preview command, so its output and CLI stability must
be reviewed when upgrading uv. `npm audit` fails the command for high or critical
findings. Do not apply automated force upgrades: inspect the advisory, reachable
usage, available fixed version, and compatibility impact, then update the direct
requirement and regenerate the relevant lockfile deliberately.

## Phase 1 review record

- Review executed: 2026-08-26 with uv 0.12.6 and npm 10.9.8.
- Scope: FastAPI/ASGI/Pydantic/HTTP/subtitle parsing for the backend foundation;
  React/Vite/TypeScript/testing/linting for the frontend foundation.
- Provider SDKs are intentionally absent. OpenAI, TMDB, SubDL, and OpenSubtitles
  dependencies are deferred until their adapters are implemented.
- Runtime package licenses and vulnerability results must be captured after the
  initial lockfiles are generated and again before a production release.
- CI quality gates do not call live providers or require repository secrets.
- `uv audit --preview` found no known vulnerabilities or adverse project
  statuses in the locked Python packages. `npm audit --audit-level=high` found
  zero vulnerabilities in the locked frontend packages.
- The installed Python metadata and npm lockfile contain no unknown third-party
  license declarations. Observed licenses are permissive, weak-copyleft, or data
  licenses: MIT variants, BSD, ISC, Apache-2.0, PSF-2.0, MPL-2.0,
  BlueOak-1.0.0, CC0-1.0, and CC-BY-4.0. Preserve required notices and
  attribution; `caniuse-lite` is the CC-BY-4.0 data package.
- The application's own license remains unspecified. This is tracked as R-21
  and blocks public distribution, not local provider-free development.

## Phase 5–7 additions

- Review updated: 2026-08-27.
- The official OpenAI Python SDK was added only with the Responses adapter; the
  lockfile is authoritative for its exact version and transitive HTTP/JSON
  packages. The SDK is imported only by infrastructure/outbound code.
- Playwright Test was added for one browser-level acceptance path. CI installs
  its Chromium runtime explicitly; unit/component tests remain in Vitest.
- SubDL uses the already-selected HTTPX runtime and adds no provider SDK.
- Default and CI tests remain offline. The two live smoke tests are skipped
  unless both the overall policy gate and adapter-specific opt-in are set.
- The 2026-08-27 online checks found no known vulnerabilities/adverse statuses
  in the locked Python environment and zero npm vulnerabilities.
- Re-run the license and online vulnerability commands before committing a
  release candidate; implementation verification alone is not a legal/license
  approval for either provider.

## Phase 8–9 additions

- Review updated: 2026-08-27.
- Added `@axe-core/playwright` as a development-only browser accessibility
  scanner; it does not enter the Vite runtime bundle.
- CI now runs both ecosystem audits, the legal-corpus and configured-limit
  performance gates, and clean multi-stage builds for both runtime images.
- Backend/frontend `.dockerignore` files exclude virtual environments,
  dependencies, tests, reports, scripts, and previous build output not needed by
  each image.
- Container base images still require registry digest/SBOM/vulnerability review
  on the immutable release artifacts. CI build success is not a vulnerability
  scan, and no particular scanner is selected until the deployment platform is
  chosen.
