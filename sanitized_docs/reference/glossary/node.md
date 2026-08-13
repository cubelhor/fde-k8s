# Node

A node is a worker machine in Kubernetes.

A worker node may be a VM or physical machine, depending on the cluster. It has local daemons or services necessary to run Pods and is managed by the control plane. The daemons on a node include kubelet, kube-proxy, and a container runtime implementing the CRI such as docker.

In early Kubernetes versions, Nodes were called "Minions".