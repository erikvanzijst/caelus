# Immich Capacity Planning Report

**Date:** 2026-03-19
**Environment:** Proxmox VM (dev-k3s), 4 vCPU, 16 GiB RAM, 0 swap, k3s single-node
**Production reference:** Separate k3s host running a real-world Immich instance (~91k assets)

---

## Executive Summary

A real-world Immich instance with ~91,000 assets consumes approximately **1.6 GiB of RAM**
after a fresh restart, rising to ~2.1 GiB over time due to V8 heap fragmentation from
background job processing. An empty, freshly deployed instance consumes approximately
**0.7–1.1 GiB**, depending on PostgreSQL buffer warmth. The dominant memory consumers are
the Immich server process and PostgreSQL.

Source code analysis confirms that **Immich holds no per-asset in-memory caches** — the
server memory growth observed on long-running instances is V8/native heap fragmentation,
not active working set. A pod restart reclaims ~580 Mi (46%) of server pod memory.

For Caelus production capacity planning, **budget 2.0 GiB per Immich instance** to
accommodate real-world usage with headroom for V8 heap growth between restarts.

---

## 1. Test Methodology

### 1.1 Test Environment

- **Host:** Proxmox VM, 4 cores (host passthrough), 16 GiB RAM, 30 GiB disk
- **OS:** Ubuntu (cloud image), kernel with builtin `virtio_balloon`
- **Orchestration:** k3s single-node cluster
- **Swap:** Disabled (0 bytes) — OOM killer is the only backstop
- **Ballooning:** Initially misconfigured (`balloon: 8000` with `memory: 16000`), causing
  the guest to see only ~7.6 GiB. Fixed by setting `balloon: 0` on the Proxmox host.

### 1.2 Approach

Six empty Immich instances were deployed via Caelus, then scaled to eleven. Memory was
measured at both points using `kubectl top`, `free`, `/proc/meminfo`, and `ps aux`. A
separate production Immich instance (~91k photos) was measured for real-world comparison.

Each Immich deployment consists of **4 pods**:

| Pod | Technology | Role |
|-----|-----------|------|
| `immich-server` | Node.js | Main API, background jobs, thumbnail generation |
| `immich-machine-learning` | Python (gunicorn/uvicorn) | CLIP embeddings, face detection/recognition |
| `valkey` (or `redis`) | Valkey/Redis | In-memory cache and job queue |
| `postgresql` | PostgreSQL 16 | Persistent storage, vector search (pgvector) |

---

## 2. Empty Instance Measurements

### 2.1 Per-Pod Breakdown — 6 Instances

Measured approximately 6 hours after deployment. Instances `31sy3b6gh`, `cw51xnf0d`, and
`gqaq9xbws` were the oldest (~6 hours). Instances `sihi632r0`, `qj6gvdyil`, and
`6gxxh7e2q` were the newest (~9 minutes).

| Instance | Server | ML | Valkey | PostgreSQL | **Total** |
|----------|-------:|---:|-------:|-----------:|----------:|
| 31sy3b6gh (oldest) | 399 Mi | 243 Mi | 12 Mi | 62 Mi | **716 Mi** |
| cw51xnf0d | 403 Mi | 266 Mi | 5 Mi | 103 Mi | **777 Mi** |
| gqaq9xbws | 409 Mi | 305 Mi | 4 Mi | 65 Mi | **783 Mi** |
| sihi632r0 (newest) | 466 Mi | 228 Mi | 3 Mi | 351 Mi | **1,048 Mi** |
| qj6gvdyil (newest) | 466 Mi | 229 Mi | 3 Mi | 383 Mi | **1,081 Mi** |
| 6gxxh7e2q (newest) | 490 Mi | 229 Mi | 3 Mi | 355 Mi | **1,077 Mi** |
| | | | | **Average** | **914 Mi** |

### 2.2 Per-Pod Breakdown — 11 Instances

Measured after scaling to 11 instances. Includes 5 additional deployments aged ~8–30
minutes.

| Instance | Server | ML | Valkey | PostgreSQL | **Total** |
|----------|-------:|---:|-------:|-----------:|----------:|
| 31sy3b6gh | 403 Mi | 236 Mi | 6 Mi | 62 Mi | **707 Mi** |
| cw51xnf0d | 406 Mi | 249 Mi | 3 Mi | 72 Mi | **730 Mi** |
| gqaq9xbws | 406 Mi | 274 Mi | 4 Mi | 68 Mi | **752 Mi** |
| 6gxxh7e2q | 496 Mi | 229 Mi | 3 Mi | 346 Mi | **1,074 Mi** |
| qj6gvdyil | 466 Mi | 229 Mi | 3 Mi | 366 Mi | **1,064 Mi** |
| sihi632r0 | 471 Mi | 228 Mi | 3 Mi | 343 Mi | **1,045 Mi** |
| 8t81essmd | 463 Mi | 229 Mi | 3 Mi | 385 Mi | **1,080 Mi** |
| h9anj0get | 455 Mi | 226 Mi | 3 Mi | 322 Mi | **1,006 Mi** |
| r5g56g424 | 1,105 Mi | 237 Mi | 3 Mi | 338 Mi | **1,683 Mi** |
| xkvefzdt3 | 471 Mi | 229 Mi | 3 Mi | 352 Mi | **1,055 Mi** |
| zyrrdzrim | 473 Mi | 228 Mi | 4 Mi | 344 Mi | **1,049 Mi** |
| | | | | **Average** | **1,022 Mi** |

### 2.3 Per-Pod Breakdown — 11 Instances After 24 Hours

A follow-up measurement taken ~24 hours after initial deployment.

| Instance | Server | ML | Valkey | PostgreSQL | **Total** |
|----------|-------:|---:|-------:|-----------:|----------:|
| 31sy3b6gh | 420 Mi | 236 Mi | 7 Mi | 98 Mi | **761 Mi** |
| cw51xnf0d | 421 Mi | 249 Mi | 4 Mi | 106 Mi | **780 Mi** |
| gqaq9xbws | 419 Mi | 275 Mi | 4 Mi | 102 Mi | **800 Mi** |
| 6gxxh7e2q | 512 Mi | 229 Mi | 4 Mi | 175 Mi | **920 Mi** |
| qj6gvdyil | 482 Mi | 229 Mi | 4 Mi | 177 Mi | **892 Mi** |
| sihi632r0 | 486 Mi | 228 Mi | 4 Mi | 175 Mi | **893 Mi** |
| 8t81essmd | 486 Mi | 229 Mi | 4 Mi | 286 Mi | **1,005 Mi** |
| h9anj0get | 482 Mi | 226 Mi | 4 Mi | 179 Mi | **891 Mi** |
| r5g56g424 | 479 Mi | 237 Mi | 4 Mi | 182 Mi | **902 Mi** |
| xkvefzdt3 | 497 Mi | 229 Mi | 4 Mi | 179 Mi | **909 Mi** |
| zyrrdzrim | 499 Mi | 228 Mi | 4 Mi | 179 Mi | **910 Mi** |
| | | | | **Average** | **878 Mi** |

### 2.4 Observations on Empty Instances

- **PostgreSQL dominates variance.** Older instances (6+ hours) settle to 62–103 Mi.
  Newer instances show 322–385 Mi as Postgres populates shared buffers during initial
  schema migration and geodata import. `shared_buffers` is configured at 512 MB.
  After 24 hours, even the newer instances settle to 175–182 Mi — higher than the
  oldest instances (98–106 Mi), suggesting a two-phase settling process.
- **Server pod outlier self-corrected.** Instance `r5g56g424` showed a server process at
  1,105 Mi in the initial measurement — more than double the typical ~450 Mi. After 24
  hours it dropped to 479 Mi without a restart, confirming this was a transient startup
  spike. V8's garbage collector eventually returned the pages on this idle instance.
- **ML pods are stable.** Machine learning pods consistently use 226–305 Mi regardless
  of age, as they load fixed-size models (CLIP, face detection) on startup.
- **Valkey is negligible.** 3–7 Mi across all instances at 24 hours.
- **Steady-state for empty instances: ~880 Mi** (average after 24 hours).
- **Startup peak for empty instances: ~1,050–1,080 Mi** (typical), up to ~1,683 Mi
  (worst observed, transient).

#### Empty Instance Averages Over Time

| Measurement | Age | Average | Notes |
|-------------|-----|--------:|-------|
| 6 instances | ~6 hours | 914 Mi | Mixed settled/fresh Postgres |
| 11 instances | ~30 minutes | 1,022 Mi | Mostly fresh Postgres, includes outlier |
| 11 instances | ~24 hours | **878 Mi** | Postgres settled, outlier resolved |

### 2.5 Empty Instance PostgreSQL Profile

Database size: **134 MB** (entirely geodata and schema overhead).

| Table/Index | Size |
|-------------|-----:|
| geodata_places | 113 MB |
| idx_geodata_places_alternate_names | 31 MB |
| IDX_geodata_gist_earthcoord | 21 MB |
| naturalearth_countries | 8.8 MB |
| idx_geodata_places_name | 7.7 MB |
| idx_geodata_places_admin2_name | 7.6 MB |
| idx_geodata_places_admin1_name | 5.5 MB |
| geodata_places_pkey | 4.4 MB |
| asset | 152 kB |
| face_search | 120 kB |

The geodata tables (~113 MB) are loaded on first startup and represent the fixed baseline
cost for every instance. The actual asset, embedding, and index tables are essentially
empty.

---

## 3. Real-World Instance Measurements

### 3.1 Instance Profile

- **Assets:** 90,666
- **CLIP embeddings (smart_search):** 89,988 rows
- **Face embeddings (face_search):** 84,756 rows
- **Recognized persons:** 3,113
- **Database size:** 1,673 MB
- **Pod age:** 14 days (server, ML), 44 days (Postgres, Redis)
- **PostgreSQL shared_buffers:** 512 MB

### 3.2 Per-Pod Memory (Before Restart — 14 Days Uptime)

| Pod | Memory |
|-----|-------:|
| immich-server | **1,264 Mi** |
| immich-machine-learning | **266 Mi** |
| redis | **7 Mi** |
| postgresql | **619 Mi** |
| **Total** | **2,156 Mi** |

### 3.3 PostgreSQL Table Breakdown

| Table | Size | Description |
|-------|-----:|-------------|
| smart_search | 506 MB | CLIP vector embeddings (768-dim float32, one per asset) |
| face_search | 473 MB | Face recognition embeddings (one per detected face) |
| asset | 293 MB | Core asset metadata (90,666 rows) |
| asset_file | 114 MB | File path references and variants |
| geodata_places | 114 MB | Reverse geocoding data (static, same as empty) |
| asset_exif | 33 MB | EXIF metadata extracted from photos |
| asset_ocr | 32 MB | OCR text extraction results |
| asset_face | 21 MB | Face-to-person mapping |
| tag_asset | 20 MB | Tag associations |
| asset_job_status | 13 MB | Background job tracking |
| album_asset | 12 MB | Album membership |
| ocr_search | 12 MB | OCR search index |

**Key insight:** The two vector tables (`smart_search` + `face_search`) account for
**979 MB** — 58% of the entire database. These grow linearly with asset count
and number of detected faces. At ~91k assets:

- CLIP vectors: ~5.6 kB/asset (506 MB / 89,988 rows)
- Face vectors: ~5.6 kB/face (473 MB / 84,756 rows)
- Core asset metadata: ~3.2 kB/asset (293 MB / 90,666 rows)

### 3.4 Empty vs Real-World Comparison

| Component | Empty (24h steady-state) | Real-world (pre-restart) | Real-world (post-restart) |
|-----------|-------------------------:|-------------------------:|--------------------------:|
| Server | ~470 Mi | 1,264 Mi | **681 Mi** |
| Machine Learning | ~240 Mi | 266 Mi | 266 Mi |
| Valkey/Redis | ~4 Mi | 7 Mi | 7 Mi |
| PostgreSQL | ~170 Mi | 619 Mi | 632 Mi |
| **Total** | **~880 Mi** | **2,156 Mi** | **1,586 Mi** |

The ML and Redis/Valkey pods are effectively **fixed costs** — they don't scale with data
volume. Memory growth is driven by:

1. **PostgreSQL** (+462 Mi over empty): shared_buffers (512 MB) fills with hot vector
   data. The database is 1.67 GB, so the 512 MB buffer pool is fully utilized and the
   working set exceeds it. This is **legitimate** memory use that persists across restarts.
2. **Immich Server** (+211 Mi over empty, post-restart): a modest increase reflecting
   the slightly larger NestJS bootstrap footprint when connecting to a database with
   91k assets. The much larger pre-restart figure (+814 Mi) was V8 heap fragmentation
   (see Section 3.5).

### 3.5 Server Pod Deep Dive: Process Architecture and Memory

The `immich-server` container runs **three processes** under `tini` (PID 1):

| Process | Role |
|---------|------|
| `immich` | Main process + **microservices worker thread** (background jobs: thumbnail generation, CLIP embedding, face detection, metadata extraction) |
| `immich-api` | HTTP API server (forked as a separate child process) |

The `immich` process spawns the API as a `fork()` child (separate PID and memory) but runs
the microservices worker as a `Worker` **thread** (shared memory space). This means the
`immich` process RSS includes all background job processing memory.

#### Per-Process Memory: Before and After Restart

| Process | Metric | Before restart (14d uptime) | After restart (~2 min) | Delta |
|---------|--------|----------------------------:|-----------------------:|------:|
| `immich` | RssAnon | 872 Mi | 233 Mi | **-639 Mi** |
| `immich` | VmHWM | 1,049 Mi | 465 Mi | — |
| `immich-api` | RssAnon | 260 Mi | 254 Mi | -6 Mi |
| `immich-api` | VmHWM | 364 Mi | 329 Mi | — |
| **Container total** | `kubectl top` | **1,264 Mi** | **681 Mi** | **-583 Mi** |

The restart reduced total server pod memory by **46%**. Nearly all of the reduction came
from the `immich` main process (which hosts the microservices worker). The `immich-api`
process was essentially unchanged.

### 3.6 Source Code Analysis: No Per-Asset In-Memory Caches

An analysis of the Immich server source code (NestJS, Kysely, BullMQ) was conducted to
determine whether the server maintains in-memory state that grows with asset count.

**Finding: Immich holds no significant per-asset caches in memory.**

Key observations:

1. **No ORM identity map.** Immich has fully migrated from TypeORM to **Kysely** (a
   lightweight query builder). Kysely returns plain objects, not tracked entities — there
   is no identity map that accumulates references to loaded assets.

2. **All explicit caches are fixed-size:**
   - `SearchService.embeddingCache`: LRU map capped at 100 entries (for text search
     query embeddings, not asset data)
   - `SystemConfig` cache: single object
   - `ConfigRepository` env cache: single object
   - `sharp.cache({ files: 0 })`: image processing cache explicitly disabled

3. **BullMQ job state lives in Redis, not in-process.** Completed jobs are removed
   (`removeOnComplete: true`). Failed jobs persist in Redis only. The Worker objects
   are lightweight and constant per queue.

4. **Database sessions are not long-lived.** Each repository method executes a query via
   `@InjectKysely()` and returns results directly. The `postgres.js` driver manages a
   connection pool but does not cache query results.

**Conclusion:** The ~639 Mi of excess memory in the long-running `immich` process was
**V8 heap fragmentation and native allocator bloat** from processing ~91k assets worth of
background jobs (metadata extraction via exiftool-vendored, thumbnail generation via
sharp/libvips, ML inference requests). V8's generational garbage collector reclaims
objects but rarely returns freed heap pages to the OS. This is a well-known Node.js
characteristic, not an Immich-specific issue.

The memory does **not** grow proportionally with library size on an ongoing basis. It
grows with **processing activity** and then plateaus. A pod restart fully reclaims it.

---

## 4. System Overhead (Non-Immich)

These measurements come from the dev-k3s test host and represent the fixed platform cost
that must be subtracted from available RAM before calculating Immich capacity.

### 4.1 Kubernetes and Platform Pods

| Component | Memory |
|-----------|-------:|
| Keycloak (Java, identity provider) | 847 Mi |
| Caelus worker (prod) | 263 Mi |
| Caelus worker (dev) | 158 Mi |
| Traefik (ingress controller) | 124 Mi |
| Caelus API (prod) | 87 Mi |
| Caelus API (dev) | 83 Mi |
| CoreDNS | 72 Mi |
| metrics-server | 75 Mi |
| Caelus echo (dev) | 70 Mi |
| local-path-provisioner | 49 Mi |
| Caelus PostgreSQL (dev) | 52 Mi |
| Keycloak PostgreSQL | 45 Mi |
| Caelus PostgreSQL (prod) | 35 Mi |
| Caelus echo (prod) | 22 Mi |
| SMTP mailer | 17 Mi |
| Caelus UI (prod + dev) | 10 Mi |
| oauth2-proxy (prod + dev) | 12 Mi |
| svclb-traefik | 2 Mi |
| **Subtotal (pods)** | **~2,022 Mi** |

### 4.2 System Processes (Outside Containers)

| Process | Memory |
|---------|-------:|
| k3s-server | ~665–788 Mi |
| containerd | ~200 Mi |
| **Subtotal (system)** | **~900–1,000 Mi** |

### 4.3 Kernel Overhead

| Component | Memory |
|---------|-------:|
| Slab (unreclaimable) | ~178–236 Mi |
| Page tables | ~126 Mi |
| Kernel stacks | ~23 Mi |
| vmalloc | ~37 Mi |
| min_free_kbytes reserve | 66 Mi |
| **Subtotal (kernel)** | **~430–490 Mi** |

### 4.4 Total Platform Overhead

On the 16 GiB dev-k3s host: **~3,350–3,500 Mi** is consumed before any Immich pods.
This includes Caelus itself, Keycloak, kube-system, and kernel overhead.

---

## 5. Capacity Model

### 5.1 Formula

```
max_instances = (total_ram - platform_overhead - safety_margin) / ram_per_instance
```

### 5.2 Per-Instance RAM Estimates

| Scenario | Per Instance | Notes |
|----------|-------------:|-------|
| Empty (steady-state) | ~880 Mi | Postgres settled after 24h, no user data |
| Empty (startup peak) | ~1,080 Mi | Postgres warming shared_buffers |
| Empty (worst-case spike) | ~1,680 Mi | Observed server process spike |
| Real-world, post-restart (~91k assets) | ~1,586 Mi | Freshly restarted, production instance |
| Real-world, aged (~91k assets) | ~2,156 Mi | 14 days uptime, V8 heap fragmented |
| **Recommended budget** | **2,048 Mi (2.0 GiB)** | Post-restart real-world + ~30% headroom |

### 5.3 Component-Level Scaling Model

Source code analysis (Section 3.6) confirmed that the Immich server holds **no per-asset
in-memory caches**. Server pod memory growth on long-running instances is V8 heap
fragmentation from job processing, not active working set. This means the server
component's variable cost is near zero for capacity planning purposes (assuming periodic
restarts or rolling deployments).

The primary variable cost is **PostgreSQL**, which grows with the number of stored assets
and their vector embeddings.

| Component | Fixed Cost | Variable Cost | Notes |
|-----------|------------|---------------|-------|
| ML pod | ~250 Mi | ~0 | Fixed model size (CLIP, face detection) |
| Valkey/Redis | ~5 Mi | ~0 | Negligible unless heavy job queuing |
| Server pod | ~450 Mi | ~2.5 kB/asset | Modest growth from DB query results at startup; no persistent caches |
| PostgreSQL | ~70 Mi | ~6 kB/asset | Capped by shared_buffers (512 MB); DB grows at ~15 kB/asset on disk |
| **Total** | **~775 Mi** | **~8.5 kB/asset** | |

Using this model:

- 0 assets: ~775 Mi (measured steady-state after 24h: ~880 Mi)
- 50,000 assets: ~1,190 Mi
- 91,000 assets: ~1,549 Mi (measured post-restart: 1,586 Mi — good fit)
- 100,000 assets: ~1,625 Mi

PostgreSQL RSS growth is **capped by shared_buffers** (512 MB). Once the database exceeds
the buffer pool size, Postgres evicts cold pages rather than growing further. At ~91k
assets the database is 1.67 GB but Postgres RSS is only 632 Mi (shared_buffers + connection
overhead). This means PostgreSQL memory usage plateaus around 600–650 Mi regardless of
library size, as long as shared_buffers remains at 512 MB.

**Note on V8 heap bloat:** Long-running server pods accumulate ~500–650 Mi of unreturned
V8 heap over weeks of operation. This is reclaimed by a pod restart. For capacity planning,
either budget for it (~2.1 GiB) or implement periodic rolling restarts to keep memory
in the ~1.6 GiB range.

### 5.4 Example: 16 GiB Host

```
Total RAM:          15,615 Mi
Platform overhead:  ~3,400 Mi  (k3s, Caelus, Keycloak, kube-system, kernel)
Available:          ~12,215 Mi
Safety margin:      ~500 Mi    (OOM avoidance with 0 swap)
Usable:             ~11,715 Mi

Empty instances:    11,715 / 1,080 = 10.8 → 10 safe (startup), 16 at steady-state
Real-world (2.0G):  11,715 / 2,048 =  5.7 → 5 safe
Real-world (no restart budget): 11,715 / 2,560 = 4.6 → 4 safe
```

### 5.5 Validated Predictions

| Scenario | Predicted | Actual |
|----------|-----------|--------|
| Max empty instances on 16 GiB (startup) | 10–11 | 11 deployed, stable at 1,404 Mi remaining |
| 12th instance | "very risky, ~350 Mi headroom" | Not yet tested |
| Server pod restart reclaims fragmented memory | ~650 Mi reduction | 583 Mi reduction (46%) |
| Post-restart real-world instance | ~1.3–1.5 GiB | 1,586 Mi (1.55 GiB) |

---

## 6. Recommendations

1. **Budget 2.0 GiB per real-world Immich instance** for capacity planning. This
   accommodates a moderately-sized library (~50–100k assets) with headroom for V8 heap
   growth. If periodic restarts are not feasible, budget 2.5 GiB to cover long-running
   heap fragmentation.

2. **Consider periodic server pod restarts.** The Immich server accumulates ~500–650 Mi
   of V8 heap fragmentation over weeks of operation. Source code analysis confirms this
   is not useful cached state — it is unreturned heap pages from processed background
   jobs. A rolling restart (e.g., weekly via a CronJob or deployment rollout) reclaims
   this memory at the cost of a brief restart (~30–60 seconds). This is the single most
   effective way to improve memory density.

3. **PostgreSQL shared_buffers is the key tunable.** It defaults to 512 MB. For
   constrained environments, reducing this to 256 MB would save ~250 Mi per instance
   at the cost of more disk I/O for vector similarity searches.

4. **Always provision swap** on production hosts. With 0 swap, a single pod spiking
   (as observed with r5g56g424 at 1,683 Mi) can trigger the OOM killer and bring down
   unrelated workloads including k3s itself. Even 1–2 GiB of swap provides a critical
   buffer.

5. **Set Kubernetes resource limits.** None of the Immich pods in these tests had memory
   limits configured. Adding limits (e.g., 1.0 GiB for server, 512 Mi for ML, 768 Mi
   for PostgreSQL) would allow Kubernetes to OOM-kill individual pods rather than having
   the kernel OOM-kill system processes. This also naturally addresses V8 heap
   fragmentation — when the server pod hits its limit, Kubernetes restarts it, reclaiming
   the bloated heap.

6. **Monitor vector table growth.** The CLIP and face embedding tables grow linearly
   and dominate PostgreSQL storage. At ~11 kB per asset (combined), a 500k-asset library
   would produce ~5.5 GB of vector data alone, far exceeding the default shared_buffers.

---

## Appendix A: Server Pod Restart Experiment

A controlled restart of the production Immich server pod (91k assets, 14 days uptime) was
performed to validate the V8 heap fragmentation hypothesis.

**Before restart** (pod `immich-server-865cc978bc-zk597`, 14 days old):

| Metric | `immich` (PID 8) | `immich-api` (PID 32) |
|--------|------------------:|----------------------:|
| VmRSS | 943 Mi | 328 Mi |
| RssAnon | 872 Mi | 260 Mi |
| VmHWM | 1,049 Mi | 364 Mi |

**After restart** (pod `immich-server-865cc978bc-m5n4p`, ~2 minutes old):

| Metric | `immich` (PID 7) | `immich-api` (PID 31) |
|--------|------------------:|----------------------:|
| VmRSS | 304 Mi | 322 Mi |
| RssAnon | 233 Mi | 254 Mi |
| VmHWM | 465 Mi | 329 Mi |

**Container-level (`kubectl top`):**

| | Before | After | Change |
|--|-------:|------:|-------:|
| immich-server | 1,264 Mi | 681 Mi | **-583 Mi (-46%)** |
| postgresql | 619 Mi | 632 Mi | +13 Mi |
| machine-learning | 266 Mi | 266 Mi | unchanged |
| redis | 7 Mi | 7 Mi | unchanged |
| **Instance total** | **2,156 Mi** | **1,586 Mi** | **-570 Mi (-26%)** |

The `immich` process dropped from 872 Mi to 233 Mi RssAnon — a **639 Mi reduction** (73%).
The `immich-api` process was effectively unchanged (260 → 254 Mi). This confirms that the
memory growth is entirely within the microservices worker thread (background job processing)
and is V8 heap fragmentation, not active caches.

## Appendix B: Kernel OOM Thresholds

| Parameter | Value |
|-----------|-------|
| min_free_kbytes | 67,584 kB (66 Mi) |
| Zone watermark (min) | 66 Mi |
| Zone watermark (low) | 82 Mi |
| Zone watermark (high) | 99 Mi |
| Swap | 0 (disabled) |

With no swap, the OOM killer fires when the kernel cannot reclaim enough pages to satisfy
an allocation after exhausting page cache eviction and slab shrinking. The `min` watermark
(66 Mi) is the absolute floor — when free memory drops below this, direct reclaim blocks
all allocations and OOM becomes imminent.

## Appendix C: Speculative — Shared Component Architecture

This appendix explores potential memory savings from sharing components across Immich
instances. These optimizations require modifications to Immich's deployment architecture
and carry significant operational complexity. They are included here for capacity planning
purposes only.

**Baseline:** A dedicated real-world Immich instance (post-restart, ~91k assets) consumes
~1,586 Mi across 4 pods.

### Shared PostgreSQL

Each Immich instance runs a dedicated PostgreSQL pod consuming ~632 Mi, dominated by the
`shared_buffers` allocation (512 MB). This is a per-process, fixed-size memory pool
regardless of how much data the instance holds.

Consolidating N instances into a single PostgreSQL server (each with its own database or
schema) would eliminate N-1 redundant shared_buffers allocations. A single Postgres with
`shared_buffers: 1024` could plausibly serve ~10 instances at ~1.2 GiB total, compared
to 10 × 632 Mi = 6.2 GiB with dedicated pods.

**Estimated savings: ~500 Mi per instance** (after the first).

Risks and trade-offs:

- **Buffer pool contention.** Vector similarity searches (CLIP, face recognition) are
  the hottest queries and benefit heavily from cached pages. With a shared buffer pool,
  one user's search can evict another's hot vector data, degrading query latency.
- **Connection overhead.** Each Immich instance opens ~10 connections. At scale, the
  shared Postgres may need `max_connections` tuned upward, with each connection consuming
  ~5–10 Mi of per-backend memory.
- **Failure blast radius.** A single Postgres crash or misconfigured migration affects
  all instances simultaneously.
- **Backup/restore complexity.** Per-instance backup and restore becomes more involved
  with shared databases.

### Shared Machine Learning Pod

The ML pod is **stateless** — it loads fixed-size models (CLIP for image/text embeddings,
face detection/recognition) into memory on startup and serves inference over HTTP. Every
Immich instance runs identical models and identical versions.

A single ML pod could serve N instances with zero code changes to Immich — only the
`IMMICH_MACHINE_LEARNING_URL` environment variable needs to point to the shared service.

**Estimated savings: ~250 Mi per instance** (after the first).

Risks and trade-offs:

- **Throughput bottleneck.** ML inference is CPU-bound. During bulk photo imports,
  multiple instances competing for the same ML pod would see slower embedding generation.
  This affects only background processing speed, not user-facing functionality.
- **Version coupling.** All instances sharing an ML pod must run compatible Immich
  versions. Model updates (e.g., a new CLIP model) would affect all instances
  simultaneously.
- **Single point of failure.** If the shared ML pod crashes, all instances lose ML
  functionality (search, face recognition) until it recovers.
- **Mitigation.** Running 2 replicas behind a Service would address availability at the
  cost of ~250 Mi, still far less than N dedicated pods.

### Shared Valkey/Redis

Each Valkey pod consumes only 3–7 Mi. Consolidation would require key namespacing or
separate Redis databases (SELECT 0–15) to prevent BullMQ queue collisions between
instances.

**Estimated savings: ~5 Mi per instance.** Not worth the complexity.

### Combined Impact

| Component | Dedicated (per instance) | Shared (marginal cost) | Savings |
|-----------|-------------------------:|-----------------------:|--------:|
| Server | 681 Mi | 681 Mi | — |
| Machine Learning | 250 Mi | ~0 Mi (amortized) | ~250 Mi |
| PostgreSQL | 632 Mi | ~130 Mi (amortized) | ~500 Mi |
| Valkey/Redis | 7 Mi | 7 Mi | — |
| **Total** | **1,570 Mi** | **~818 Mi** | **~750 Mi** |

The first instance pays the full cost (~1,570 Mi + shared Postgres base + shared ML base
≈ ~2,200 Mi). Each additional instance costs only **~818 Mi** — roughly half the
dedicated cost.

**Projected density on a 16 GiB host** (~12,215 Mi usable after platform overhead):

| Architecture | Per instance | Max instances |
|--------------|------------:|--------------:|
| Fully dedicated (current) | ~1,586 Mi | 5–6 |
| Shared ML only | ~1,336 Mi | 7–8 |
| Shared ML + PostgreSQL | ~818 Mi | ~13 |

The server pod (~681 Mi) is the irreducible per-instance cost. It contains Immich's
application logic, authentication, job scheduling, and API — effectively the entire
application. Sharing it would require making Immich itself multi-tenant, which is a
fundamentally different product architecture.

### Feasibility Assessment

| Optimization | Complexity | Risk | Savings | Recommendation |
|-------------|-----------|------|---------|---------------|
| Shared ML pod | Low | Low | ~250 Mi/instance | Worth pursuing first |
| Shared PostgreSQL | Medium | Medium | ~500 Mi/instance | High impact, requires careful testing |
| Shared Valkey | Medium | Low | ~5 Mi/instance | Not worth it |
| Multi-tenant server | Very high | Very high | ~681 Mi/instance | Not recommended |
