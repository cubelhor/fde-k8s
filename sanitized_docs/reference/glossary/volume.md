# Volume

A directory containing data, accessible to the containers in a pod.

A Kubernetes volume lives as long as the Pod that encloses it. Consequently, a volume outlives any containers that run within the Pod, and data in the volume is preserved across container restarts.

See [storage](/docs/concepts/storage/) for more information.