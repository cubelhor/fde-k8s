# HostAliases

A HostAliases is a mapping between the IP address and hostname to be injected into a Pod's hosts file.

[HostAliases](/docs/reference/generated/kubernetes-api//#hostalias-v1-core) is an optional list of hostnames and IP addresses that will be injected into the Pod's hosts file if specified. This is only valid for non-hostNetwork Pods.