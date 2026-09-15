# ReplicaSet

A ReplicaSet (aims to) maintain a set of replica Pods running at any given time.

Workload objects such as deployment make use of ReplicaSets
to ensure that the configured number of Pods are
running in your cluster, based on the spec of that ReplicaSet.