# Aggregation Layer

The aggregation layer lets you install additional Kubernetes-style APIs in your cluster.

When you've configured the Kubernetes API Server to [support additional APIs](/docs/tasks/extend-kubernetes/configure-aggregation-layer/), you can add `APIService` objects to "claim" a URL path in the Kubernetes API.