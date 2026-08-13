# DisableCPUQuotaWithExclusiveCPUs

When the feature gate `DisableCPUQuotaWithExclusiveCPUs` is enabled (the default), then Kubernetes
does **not** enforce CPU quota for Pods that use the [Guaranteed](/docs/concepts/workloads/pods/pod-qos/#guaranteed)
QoS class.

You can disable the `DisableCPUQuotaWithExclusiveCPUs` feature gate to restore the legacy behavior.