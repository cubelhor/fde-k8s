# Preemption

Preemption logic in Kubernetes helps a pending pod to find a suitable node by evicting low priority Pods existing on that Node.

If a Pod cannot be scheduled, the scheduler tries to [preempt](/docs/concepts/scheduling-eviction/pod-priority-preemption/#preemption) lower priority Pods to make scheduling of the pending Pod possible.