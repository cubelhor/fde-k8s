# Upgrading Linux nodes

This page explains how to upgrade a Linux Worker Nodes created with kubeadm.

## 

 
* Familiarize yourself with [the process for upgrading the rest of your kubeadm
cluster](/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade). You will want to
upgrade the control plane nodes before upgrading your Linux Worker nodes.

## Changing the package repository

If you're using the community-owned package repositories (`pkgs.k8s.io`), you need to 
enable the package repository for the desired Kubernetes minor release. This is explained in
[Changing the Kubernetes package repository](/docs/tasks/administer-cluster/kubeadm/change-package-repository/)
document.

## Upgrading worker nodes

### Upgrade kubeadm

Upgrade kubeadm:

```shell
# replace x in .x-* with the latest patch version
sudo apt-mark unhold kubeadm && \
sudo apt-get update && sudo apt-get install -y kubeadm='.x-*' && \
sudo apt-mark hold kubeadm
```

For systems with DNF:
```shell
# replace x in .x-* with the latest patch version
sudo yum install -y kubeadm-'.x-*' --disableexcludes=kubernetes
```
For systems with DNF5:
```shell
# replace x in .x-* with the latest patch version
sudo yum install -y kubeadm-'.x-*' --setopt=disable_excludes=kubernetes
```

### Call "kubeadm upgrade"

For worker nodes this upgrades the local kubelet configuration:

```shell
sudo kubeadm upgrade node
```

### Drain the node

Prepare the node for maintenance by marking it unschedulable and evicting the workloads:

```shell
# execute this command on a control plane node
# replace <node-to-drain> with the name of your node you are draining
kubectl drain <node-to-drain> --ignore-daemonsets
```

### Upgrade kubelet and kubectl

1. Upgrade the kubelet and kubectl:

   
   
   ```shell
   # replace x in .x-* with the latest patch version
   sudo apt-mark unhold kubelet kubectl && \
   sudo apt-get update && sudo apt-get install -y kubelet='.x-*' kubectl='.x-*' && \
   sudo apt-mark hold kubelet kubectl
   ```
   
   
   For systems with DNF:
   ```shell
   # replace x in .x-* with the latest patch version
   sudo yum install -y kubelet-'.x-*' kubectl-'.x-*' --disableexcludes=kubernetes
   ```
   For systems with DNF5:
   ```shell
   # replace x in .x-* with the latest patch version
   sudo yum install -y kubelet-'.x-*' kubectl-'.x-*' --setopt=disable_excludes=kubernetes
   ```
   
   

1. Restart the kubelet:

   ```shell
   sudo systemctl daemon-reload
   sudo systemctl restart kubelet
   ```

### Uncordon the node

Bring the node back online by marking it schedulable:

```shell
# execute this command on a control plane node
# replace <node-to-uncordon> with the name of your node
kubectl uncordon <node-to-uncordon>
```

## 

* See how to [Upgrade Windows nodes](/docs/tasks/administer-cluster/kubeadm/upgrading-windows-nodes/).