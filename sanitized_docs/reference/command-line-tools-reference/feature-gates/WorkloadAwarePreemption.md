# WorkloadAwarePreemption

Enables the support for [Workload-aware preemption](/docs/concepts/scheduling-eviction/workload-aware-preemption/).

When enabled, if a PodGroup fails to schedule, the scheduler will use a workload-aware preemption
algorithm to select victims to preempt instead of the default pod preemption algorithm.