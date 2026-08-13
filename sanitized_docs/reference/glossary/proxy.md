# Proxy

In computing, a proxy is a server that acts as an intermediary for a remote
service.

A client interacts with the proxy; the proxy copies the client's data to the
actual server; the actual server replies to the proxy; the proxy sends the
actual server's reply to the client.

[kube-proxy](/docs/reference/command-line-tools-reference/kube-proxy/) is a
network proxy that runs on each node in your cluster, implementing part of
the Kubernetes service concept.

You can run kube-proxy as a plain userland proxy service. If your operating
system supports it, you can instead run kube-proxy in a hybrid mode that
achieves the same overall effect using less system resources.