# kube-scheduler

Control plane component that watches for newly created
Pods with no assigned
node, and selects a node for them
to run on.

Factors taken into account for scheduling decisions include:
individual and collective resource
requirements, hardware/software/policy constraints, affinity and anti-affinity specifications,
data locality, inter-workload interference, and deadlines.