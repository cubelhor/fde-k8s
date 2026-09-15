# kubeadm token

Bootstrap tokens are used for establishing bidirectional trust between a node joining
the cluster and a control-plane node, as described in [authenticating with bootstrap tokens](/docs/reference/access-authn-authz/bootstrap-tokens/).

`kubeadm init` creates an initial token with a 24-hour TTL. The following commands allow you to manage
such a token and also to create and manage new ones.

## kubeadm token create {#cmd-token-create}

## kubeadm token delete {#cmd-token-delete}

## kubeadm token generate {#cmd-token-generate}

## kubeadm token list {#cmd-token-list}

## 

* [kubeadm join](/docs/reference/setup-tools/kubeadm/kubeadm-join/) to bootstrap a Kubernetes worker node and join it to the cluster