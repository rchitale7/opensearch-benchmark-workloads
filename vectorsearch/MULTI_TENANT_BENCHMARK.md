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

### How I think target-throughput works

`target-throughput` in OSB is assumed to be **per client**. With 1:1 client-to-tenant mapping (32 clients = 32 tenants), the values map directly to per-tenant rates. For ingestion, it is assumed to be the rate of docs/s ingested. For search, it is assumed to be
the rate of queries/s. 

However, I am not 100% sure on this. This needs some more testing to understand what's happening. 

### Search QPS

`search_target_throughput` = desired QPS per tenant.

| Per-tenant QPS | search_target_throughput |
|---|---|
| 0.1 | 0.1 |
| 1 | 1 |
| 3 | 3 |

### Ingestion TPS

`index_target_throughput` = desired ingestion TPS per tenant.

| Per-tenant TPS | index_target_throughput |
|---|---|
| 60 | 60 |
| 80 | 80 |
| 125 | 125 |

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
