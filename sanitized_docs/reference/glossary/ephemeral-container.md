# Ephemeral Container

A container type that you can temporarily run inside a pod.

If you want to investigate a Pod that's running with problems, you can add an ephemeral container to that Pod and carry out diagnostics.
Ephemeral containers have no resource or scheduling guarantees,
and you should not use them to run any part of the workload itself.

Ephemeral containers are not supported by static pods.