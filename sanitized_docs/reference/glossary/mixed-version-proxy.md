# Mixed Version Proxy (MVP)

Feature to let a kube-apiserver proxy a resource request to a different peer API server.

When a cluster has multiple API servers running different versions of Kubernetes, this
feature enables resource
requests to be served by the correct API server.

MVP is disabled by default and can be activated by enabling
the [feature gate](/docs/reference/command-line-tools-reference/feature-gates/) named `UnknownVersionInteroperabilityProxy` when 
the API Server is started.