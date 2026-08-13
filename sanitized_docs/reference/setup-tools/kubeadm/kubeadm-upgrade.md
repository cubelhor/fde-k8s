# kubeadm upgrade

`kubeadm upgrade` is a user-friendly command that wraps complex upgrading logic
behind one command, with support for both planning an upgrade and actually performing it.

## kubeadm upgrade guidance

The steps for performing an upgrade using kubeadm are outlined in [this document](/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/).
For older versions of kubeadm, please refer to older documentation sets of the Kubernetes website.

You can use `kubeadm upgrade diff` to see the changes that would be applied to static pod manifests.

In Kubernetes v1.15.0 and later, `kubeadm upgrade apply` and `kubeadm upgrade node` will also
automatically renew the kubeadm managed certificates on this node, including those stored in kubeconfig files.
To opt-out, it is possible to pass the flag `--certificate-renewal=false`. For more details about certificate
renewal see the [certificate management documentation](/docs/tasks/administer-cluster/kubeadm/kubeadm-certs).

The commands `kubeadm upgrade apply` and `kubeadm upgrade plan` have a legacy `--config`
flag which makes it possible to reconfigure the cluster, while performing planning or upgrade of that particular
control-plane node. Please be aware that the upgrade workflow was not designed for this scenario and there are
reports of unexpected results.

## kubeadm upgrade plan {#cmd-upgrade-plan}

## kubeadm upgrade apply  {#cmd-upgrade-apply}

## kubeadm upgrade diff {#cmd-upgrade-diff}

## kubeadm upgrade node {#cmd-upgrade-node}

## 

* [kubeadm config](/docs/reference/setup-tools/kubeadm/kubeadm-config/) if you initialized your cluster using kubeadm v1.7.x or lower, to configure your cluster for `kubeadm upgrade`