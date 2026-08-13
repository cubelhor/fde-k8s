# Taint

A core object consisting of three required properties: key, value, and effect. Taints prevent the scheduling of Pods on nodes or node groups.

Taints and tolerations work together to ensure that pods are not scheduled onto inappropriate nodes. One or more taints are applied to a node. A node should only schedule a Pod with the matching tolerations for the configured taints.