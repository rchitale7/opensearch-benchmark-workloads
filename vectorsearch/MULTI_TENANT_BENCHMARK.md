# Multi-Tenant KNN Benchmark - How to Run

## Prerequisites

- OpenSearch Benchmark installed (`opensearch-benchmark` command available)
- Access to an OpenSearch domain (2.19 or 3.3)
- The workload code from [this branch](https://github.com/rchitale7/opensearch-benchmark-workloads/tree/rchital)

## Quick Start

### 1. Smoke Test (verify setup)

```bash
opensearch-benchmark run \
  --workload-path=/path/to/vectorsearch \
  --workload-params="/path/to/params/multi_tenant/multi-tenant-smoke-test.json" \
  --test-procedure=multi-tenant-index-and-search \
  --target-hosts=https://YOUR_DOMAIN_ENDPOINT \
  --client-options="use_ssl:true,verify_certs:false,basic_auth_user:'USERNAME',basic_auth_password:'PASSWORD',timeout:1200" \
  --pipeline=benchmark-only
```

Verify all tenants got 1000 docs each:
```bash
curl -k -u USERNAME:PASSWORD "https://YOUR_DOMAIN_ENDPOINT/_cat/indices/tenant_index_*?v&s=index&h=index,docs.count"
```

### 2. Full Run

Swap the params file for the desired scenario:

```bash
opensearch-benchmark run \
  --workload-path=/path/to/vectorsearch \
  --workload-params="/path/to/params/multi_tenant/multi-tenant-qps-0.1.json" \
  --test-procedure=multi-tenant-index-and-search \
  --target-hosts=https://YOUR_DOMAIN_ENDPOINT \
  --client-options="use_ssl:true,verify_certs:false,basic_auth_user:'USERNAME',basic_auth_password:'PASSWORD',timeout:1200" \
  --pipeline=benchmark-only
```

## Params Files

| File | QPS/tenant | Vectors/tenant | Version | Notes |
|---|---|---|---|---|
| `multi-tenant-smoke-test.json` | 0.1 | 1,000 | 3.3 | Quick validation |
| `multi-tenant-qps-0.1.json` | 0.1 | 600,000 | 3.3 | Primary comparison |
| `multi-tenant-qps-1.json` | 1 | 600,000 | 3.3 | |
| `multi-tenant-qps-3.json` | 3 | 600,000 | 3.3 | |
| `multi-tenant-qps-0.1-2.19.json` | 0.1 | 600,000 | 2.19 | No derived_source |

All files use: 32 tenants, bulk size 20, 32 indexing + 32 search clients (1:1 client-to-tenant mapping).

The number of tenants is configurable. However, any modification to the number of tenants changes the number of indexing/search clients. 

## Setting Throughput

### How target-throughput works

`target-throughput` in OSB is the **total** rate across all clients. OSB divides it by the number of clients to get the per-client rate (see `UnitAwareScheduler` in `osbenchmark/worker_coordinator/scheduler.py`).

With 1:1 client-to-tenant mapping: **per-tenant rate = target-throughput / num_tenants**.

For indexing, the unit is `docs/s` (rendered as `"X docs/s"` in the schedule). For search, the unit is `ops/s` (rendered as `"X ops/s"` in the schedule).

### Search QPS

`search_target_throughput` = desired QPS per tenant × num_tenants.

| Per-tenant QPS | search_target_throughput (32 tenants) |
|---|---|
| 0.1 | 3.2 |
| 1 | 32 |
| 3 | 96 |

### Ingestion TPS

`index_target_throughput` = desired docs/s per tenant × num_tenants. Set to 0 for unthrottled.

| Per-tenant docs/s | index_target_throughput (32 tenants) |
|---|---|
| 60 | 1920 |
| 80 | 2560 |
| 125 | 4000 |

## Reading Results

From the OSB output table:

| Metric | How to read |
|---|---|
| `multi-tenant-indexing` throughput (docs/s) | ÷ num_tenants = vectors/s/tenant |
| `multi-tenant-indexing` p90 service time | Actual server processing time per bulk |
| `multi-tenant-indexing` p90 latency | Includes queue wait (high = target too aggressive) |
| `multi-tenant-indexing` error rate | Must be < 2% to pass |
| `multi-tenant-search` throughput (ops/s) | ÷ num_tenants = QPS/tenant |
| `multi-tenant-search` p90 latency | Per search request |

**Pass criteria:** error rate < 2% AND ingestion p90 < 30,000 ms.

## Utility Commands

```bash
# Delete all tenant indexes
curl -k -u USERNAME:PASSWORD -X DELETE "https://YOUR_DOMAIN_ENDPOINT/tenant_index_*"

# Check cluster health
curl -k -u USERNAME:PASSWORD "https://YOUR_DOMAIN_ENDPOINT/_cluster/health?pretty"

# Check index settings
curl -k -u USERNAME:PASSWORD "https://YOUR_DOMAIN_ENDPOINT/tenant_index_0/_settings?pretty"
```
