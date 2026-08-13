# Controller

In Kubernetes, controllers are control loops that watch the state of your
cluster, then make or request
changes where needed.
Each controller tries to move the current cluster state closer to the desired
state.

Controllers watch the shared state of your cluster through the
apiserver (part of the
control-plane).

Some controllers also run inside the control plane, providing control loops that
are core to Kubernetes' operations. For example: the deployment controller, the
daemonset controller, the namespace controller, and the persistent volume
controller (and others) all run within the
kube-controller-manager.