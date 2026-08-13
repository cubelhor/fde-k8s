# ResourceSlice

Represents one or more infrastructure resources, such as
devices, that are attached to
nodes. Drivers create and manage ResourceSlices in the cluster. ResourceSlices
are used for
[dynamic resource allocation (DRA)](/docs/concepts/scheduling-eviction/dynamic-resource-allocation/).

When a ResourceClaim is
created, Kubernetes uses ResourceSlices to find nodes that have access to
resources that can satisfy the claim. Kubernetes allocates resources to the
ResourceClaim and schedules the Pod onto a node that can access the resources.