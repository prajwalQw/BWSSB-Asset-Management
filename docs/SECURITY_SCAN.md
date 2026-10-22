# BWSSB Digital Twin — Dependency Security Audit & Vulnerability Assessment

**Scan Date**: October 22, 2026  
**Auditing Tools**: `pip-audit` (v2.7.3) & `npm audit`  
**Target Environments**:
- Backend Python Environment: Python 3.11.9, FastAPI / Starlette stack
- Frontend Node Environment: Vite + React + MapLibre GL + Deck.gl

---

## 1. Executive Summary

A comprehensive automated software supply chain audit was performed across both backend Python dependencies and frontend NPM packages to identify known CVEs, GHSA advisories, and outdated libraries.

| Scope | Total Scanned Packages | Vulnerable Packages | Severity Breakdown | Status / Remediation Plan |
| :--- | :--- | :--- | :--- | :--- |
| **Backend (Python)** | Global Python Environment | 16 packages | Moderate to High (CVEs in PIL, GitPython, urllib3, Starlette) | Production containerization will isolate minimal required dependencies (`backend/requirements.txt`) without ML packages (keras, torch). Upgrades staged for next release cycle. |
| **Frontend (NPM)** | `frontend/node_modules` | 6 direct / transitive packages | 1 Critical, 13 High, 7 Moderate | MapLibre DOM sanitizer and braces; planned for major version bump without breaking custom deck.gl tile layers. |

---

## 2. Backend Security Audit (`pip-audit`)

### Key Vulnerabilities Identified in Global Python Environment

1. **`starlette` (v1.0.0)**
   - *Advisories*: `PYSEC-2026-161`, `PYSEC-2026-2281`, `PYSEC-2026-249`
   - *Fix Version*: `1.3.1`
   - *Impact*: Fixed in next minor FastAPI release; mitigated via slowapi rate limiting and input size controls.

2. **`cryptography` (v47.0.0)**
   - *Advisories*: `GHSA-537c-gmf6-5ccf`, `PYSEC-2026-3552`, `PYSEC-2026-3553`
   - *Fix Version*: `48.0.1` / `49.0.0`
   - *Mitigation*: Used primarily for symmetric JWT token validation (`HS256`).

3. **`gitpython` (v3.1.50)**
   - *Advisories*: Multiple RCE/path traversal advisories for untrusted git repositories.
   - *Mitigation*: Digital Twin does not execute git clone operations on untrusted URLs at runtime.

4. **`pillow` (v12.2.0)**
   - *Advisories*: Image parsing loop denial of service.
   - *Mitigation*: Digital Twin backend does not accept arbitrary raster uploads from external users.

5. **`python-jose` (v3.5.0)**
   - *Advisory*: `PYSEC-2026-4298`
   - *Mitigation*: Algorithms restricted explicitly to `HS256` in `auth.py`.

---

## 3. Frontend Security Audit (`npm audit`)

### Vulnerability Findings

1. **`maplibre-gl` (<= 6.4.0) — Critical**
   - *Advisory*: `GHSA-jrc7-96c5-q579` (XSS Sanitizer Bypass in `DOM.sanitize()`)
   - *Remediation*: Direct upgrade to MapLibre GL 6.15.0 staged for UI regression testing. No user-supplied HTML strings are rendered inside map popups.

2. **`braces` / `chokidar` / `micromatch` — High**
   - *Advisory*: `GHSA-vfj7-8cjw-p6xm` (Stack-exhaustion DoS through nested patterns)
   - *Context*: Build-time development tooling dependency only; not bundled into client production assets.

3. **`fflate` (0.7.0 - 0.7.4) — Moderate**
   - *Advisory*: `GHSA-px8p-9vwx-vf98` (Infinite loop when parsing malformed ZIP64)
   - *Context*: Transitive loaders.gl dependency.

4. **`image-size` (0.6.3 - 2.0.2) — High**
   - *Advisory*: `GHSA-w3rx-r6r6-pgpr` (ICNS parser infinite loop)
   - *Context*: Transitive deck.gl texture compressor dependency.

---

## 4. Remediation Action Plan & Verification

1. **Production Dockerization**:
   - Create multi-stage slim Dockerfile containing only runtime dependencies from `requirements.txt`.
   - Strips unused global packages (`keras`, `torch`, `gitpython`) from production image.
2. **Frontend Dependency Updates**:
   - Run `npm audit fix` for non-breaking transitive dependencies.
   - Stage MapLibre GL major version upgrade in a separate testing branch to avoid regression in vector tile basemaps.
3. **Continuous Auditing**:
   - Automated CI step runs `pip-audit` and `npm audit` on every PR.
