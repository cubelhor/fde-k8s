# EndpointSlice

EndpointSlices track the IP addresses of backend endpoints.
EndpointSlices are normally associated with a
Service and the backend endpoints typically represent
Pods.

One Service can be backed by multiple Pods. Kubernetes represents the backing endpoints of a Service
with a set of EndpointSlices that are associated with that Service.
The backing endpoints are usually, but not always, pods running in the cluster.

The control plane usually manages EndpointSlices for you automatically. However,
EndpointSlices can be defined manually for Services without
selectors specified.