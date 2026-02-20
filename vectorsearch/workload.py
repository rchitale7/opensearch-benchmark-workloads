# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

from .runners import register as register_runners
from osbenchmark.workload.params import ParamSource
import random
import numpy as np
import logging


def register(registry):
    register_runners(registry)
    registry.register_param_source("random-vector-bulk-param-source", RandomBulkParamSource)
    registry.register_param_source("random-vector-search-param-source", RandomSearchParamSource)
    registry.register_param_source("multi-tenant-bulk-param-source", MultiTenantBulkParamSource)
    registry.register_param_source("multi-tenant-search-param-source", MultiTenantSearchParamSource)
    registry.register_param_source("multi-tenant-setup-param-source", MultiTenantSetupParamSource)
    registry.register_runner("multi-tenant-create-indices", MultiTenantCreateIndicesRunner(), async_runner=True)


class RandomBulkParamSource(ParamSource):
    def __init__(self, workload, params, **kwargs):
        super().__init__(workload, params, **kwargs)
        logging.getLogger(__name__).info("Workload: [%s], params: [%s]", workload, params)
        self._bulk_size = params.get("bulk-size", 100)
        self._index_name = params.get('index_name','target_index')
        self._field = params.get("field", "target_field")
        self._dims = params.get("dims", 768)
        self._partitions = params.get("partitions", 1000)

    def partition(self, partition_index, total_partitions):
        return self

    def params(self):
        bulk_data = []
        for _ in range(self._bulk_size):
            vec = np.random.rand(self._dims)
            partition_id = random.randint(0, self._partitions)
            metadata = {"_index": self._index_name}
            bulk_data.append({"create": metadata})
            bulk_data.append({"partition_id": partition_id, self._field: vec.tolist()})

        return {
            "body": bulk_data,
            "bulk-size": self._bulk_size,
            "action-metadata-present": True,
            "unit": "docs",
            "index": self._index_name,
            "type": "",
        }

class RandomSearchParamSource(ParamSource):
    def __init__(self, workload, params, **kwargs):
        super().__init__(workload, params, **kwargs)
        logging.getLogger(__name__).info("Workload: [%s], params: [%s]", workload, params)
        self._index_name = params.get('index_name', 'target_index')
        self._dims = params.get("dims", 768)
        self._cache = params.get("cache", False)
        self._top_k = params.get("k", 100)
        self._field = params.get("field", "target_field")
        self._query_body = params.get("body", {})
        self._detailed_results = params.get("detailed-results", False)

    def partition(self, partition_index, total_partitions):
        return self

    def params(self):
        query_vec = np.random.rand(self._dims).tolist()
        query = self.generate_knn_query(query_vec)
        query.update(self._query_body)
        return {"index": self._index_name, "cache": self._cache, "size": self._top_k, "body": query, "detailed-results": self._detailed_results}

    def generate_knn_query(self, query_vector):
        return {
            "query": {
                "knn": {
                    self._field: {
                        "vector": query_vector,
                        "k": self._top_k
                    }
                }
            }
        }


class MultiTenantBulkParamSource(ParamSource):
    """Distributes bulk indexing across N tenant indexes with random vectors.
    One client per tenant index."""

    def __init__(self, workload, params, **kwargs):
        super().__init__(workload, params, **kwargs)
        self._num_tenants = params.get("num_tenants", 32)
        self._index_prefix = params.get("index_prefix", "tenant_index")
        self._bulk_size = params.get("bulk-size", 100)
        self._field = params.get("field", "target_field")
        self._dims = params.get("dims", 256)
        self._vectors_per_tenant = params.get("vectors_per_tenant", 600000)
        self._vectors_sent = 0
        self._tenant_id = 0

    def partition(self, partition_index, total_partitions):
        self._tenant_id = partition_index % self._num_tenants
        return self

    def params(self):
        if self._vectors_sent >= self._vectors_per_tenant:
            raise StopIteration()

        index_name = f"{self._index_prefix}_{self._tenant_id}"
        bulk_data = []
        for _ in range(self._bulk_size):
            vec = np.random.rand(self._dims).tolist()
            bulk_data.append({"index": {"_index": index_name}})
            bulk_data.append({self._field: vec})

        self._vectors_sent += self._bulk_size

        return {
            "body": bulk_data,
            "bulk-size": self._bulk_size,
            "action-metadata-present": True,
            "unit": "docs",
            "index": index_name,
            "type": "",
        }


class MultiTenantSearchParamSource(ParamSource):
    """Distributes knn search queries. One client per tenant index."""

    def __init__(self, workload, params, **kwargs):
        super().__init__(workload, params, **kwargs)
        self._num_tenants = params.get("num_tenants", 32)
        self._index_prefix = params.get("index_prefix", "tenant_index")
        self._dims = params.get("dims", 256)
        self._k = params.get("k", 100)
        self._field = params.get("field", "target_field")
        self._tenant_id = 0

    def partition(self, partition_index, total_partitions):
        self._tenant_id = partition_index % self._num_tenants
        return self

    def params(self):
        index_name = f"{self._index_prefix}_{self._tenant_id}"
        query_vec = np.random.rand(self._dims).tolist()

        return {
            "index": index_name,
            "cache": False,
            "size": self._k,
            "body": {
                "query": {
                    "knn": {
                        self._field: {
                            "vector": query_vec,
                            "k": self._k
                        }
                    }
                }
            },
            "detailed-results": True,
        }


class MultiTenantSetupParamSource(ParamSource):
    """Provides params for multi-tenant index creation."""

    def __init__(self, workload, params, **kwargs):
        super().__init__(workload, params, **kwargs)
        self._params = params

    def partition(self, partition_index, total_partitions):
        return self

    def params(self):
        return self._params


class MultiTenantCreateIndicesRunner:
    """Creates N tenant indexes with knn vector field configuration."""

    async def __call__(self, opensearch, params):
        from osbenchmark.client import RequestContextHolder
        ctx = RequestContextHolder()

        num_tenants = params.get("num_tenants", 32)
        index_prefix = params.get("index_prefix", "tenant_index")

        # Build index body from workload params
        index_cfg = {
            "knn": True,
            "number_of_shards": params.get("target_index_primary_shards", 6),
            "number_of_replicas": params.get("target_index_replica_shards", 2),
            "refresh_interval": params.get("refresh_interval", "5s"),
        }
        if params.get("derived_source_enabled", False):
            index_cfg["knn.derived_source.enabled"] = True
        if params.get("approximate_graph_build_threshold") is not None:
            index_cfg["knn.advanced.approximate_threshold"] = params.get("approximate_graph_build_threshold")

        index_settings = {
            "settings": {
                "index": index_cfg
            },
            "mappings": {
                "properties": {
                    params.get("field", "target_field"): {
                        "type": "knn_vector",
                        "dimension": params.get("dims", 256),
                        "mode": params.get("mode", "on_disk"),
                        "compression_level": params.get("compression_level", "32x"),
                        "method": {
                            "name": "hnsw",
                            "space_type": params.get("target_index_space_type", "innerproduct"),
                            "engine": "faiss",
                            "parameters": {
                                "ef_construction": params.get("hnsw_ef_construction", 512),
                                "ef_search": params.get("hnsw_ef_search", 100)
                            }
                        }
                    }
                }
            }
        }

        for i in range(num_tenants):
            index_name = f"{index_prefix}_{i}"
            ctx.on_client_request_start()
            await opensearch.indices.delete(index=index_name, ignore=[404])
            await opensearch.indices.create(index=index_name, body=index_settings)
            ctx.on_client_request_end()

        return {"success": True, "weight": 1, "unit": "ops"}

    def __repr__(self):
        return "multi-tenant-create-indices"
