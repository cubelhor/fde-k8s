# Deployment

An API object that manages a replicated application, typically by running Pods with no local state.

 

Each replica is represented by a pod, and the Pods are distributed among the 
nodes of a cluster.
For workloads that do require local state, consider using a StatefulSet.