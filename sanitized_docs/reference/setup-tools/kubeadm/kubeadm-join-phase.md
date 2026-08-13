# kubeadm join phase

`kubeadm join phase` enables you to invoke atomic steps of the join process.
Hence, you can let kubeadm do some of the work and you can fill in the gaps
if you wish to apply customization.

`kubeadm join phase` is consistent with the [kubeadm join workflow](/docs/reference/setup-tools/kubeadm/kubeadm-join/#join-workflow),
and behind the scene both use the same code.

## kubeadm join phase {#cmd-join-phase}

## kubeadm join phase preflight {#cmd-join-phase-preflight}

Using this phase you can execute preflight checks on a joining node.

## kubeadm join phase control-plane-prepare {#cmd-join-phase-control-plane-prepare}

Using this phase you can prepare a node for serving a control-plane.

## kubeadm join phase kubelet-start {#cmd-join-phase-kubelet-start}

Using this phase you can write the kubelet settings, certificates and (re)start the kubelet.

## kubeadm join phase etcd-join {#cmd-join-phase-etcd-join}

Join the new etcd member to the etcd cluster.

## kubeadm join phase control-plane-join {#cmd-join-phase-control-plane-join}

Using this phase you can join a node as a control-plane instance.

## kubeadm join phase wait-control-plane {#cmd-join-wait-control-plane}

Wait for the control plane components to start.

## 

* [kubeadm init](/docs/reference/setup-tools/kubeadm/kubeadm-init/) to bootstrap a Kubernetes control-plane node
* [kubeadm join](/docs/reference/setup-tools/kubeadm/kubeadm-join/) to connect a node to the cluster
* [kubeadm reset](/docs/reference/setup-tools/kubeadm/kubeadm-reset/) to revert any changes made to this host by `kubeadm init` or `kubeadm join`
* [kubeadm alpha](/docs/reference/setup-tools/kubeadm/kubeadm-alpha/) to try experimental functionality