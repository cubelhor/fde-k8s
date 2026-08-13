# Device Plugin

Device plugins run on worker
Nodes and provide
Pods with access to
infrastructure resources,
such as local hardware, that require vendor-specific initialization or setup
steps.

Device plugins advertise resources to the
kubelet, so that workload
Pods can access hardware features that relate to the Node where that Pod is running.
You can deploy a device plugin as a daemonset,
or install the device plugin software directly on each target Node.

See
[Device Plugins](/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
for more information.