# ReplicationController

A workload management object
that manages a replicated application, ensuring that
a specific number of instances of a Pod are running.

The control plane ensures that the defined number of Pods are running, even if some
Pods fail, if you delete Pods manually, or if too many are started by mistake.

> **Note:** ReplicationController is deprecated. See
Deployment, which is similar.