# Operator pattern

The [operator pattern](/docs/concepts/extend-kubernetes/operator/) is a system
design that links a controller to one or more custom
resources.

You can extend Kubernetes by adding controllers to your cluster, beyond the built-in
controllers that come as part of Kubernetes itself.

If a running application acts as a controller and has API access to carry out tasks
against a custom resource that's defined in the control plane, that's an example of
the Operator pattern.