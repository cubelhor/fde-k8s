# WindowsEndpointSliceProxying

When enabled, kube-proxy running on Windows will use
EndpointSlices as the primary data source instead of Endpoints, enabling scalability and
performance improvements. See
[Enabling Endpoint Slices](/docs/concepts/services-networking/endpoint-slices/).