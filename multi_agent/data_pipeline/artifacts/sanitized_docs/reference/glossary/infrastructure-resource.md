# Resource (infrastructure)

Capabilities provided to one or more nodes (CPU, memory, GPUs, etc), and made available for consumption by
Pods running on those nodes.

Kubernetes also uses the term _resource_ to describe an API resource.

Computers provide fundamental hardware facilities: processing power, storage memory, network, etc.
These resources have finite capacity, measured in a unit applicable to that resource (number of CPUs, bytes of memory, etc).
Kubernetes abstracts common [resources](/docs/concepts/configuration/manage-resources-containers/)
for allocation to workloads and utilizes operating system primitives (for example, Linux cgroups) to manage consumption by workloads).

You can also use [dynamic resource allocation](/docs/concepts/scheduling-eviction/dynamic-resource-allocation/) to
manage complex resource allocations automatically.