# Condition

A condition is a field in a Kubernetes resource's status that describes the current state of that resource.

Conditions provide a standardized way for Kubernetes components to communicate the status of resources. Each condition has a `type`, a `status` (True, False, or Unknown), and optional fields like `reason` and `message` that provide additional details. For example, a Pod might have conditions like `Ready`, `ContainersReady`, or `PodScheduled`.