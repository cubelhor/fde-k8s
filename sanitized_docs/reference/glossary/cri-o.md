# CRI-O

A tool that lets you use OCI container runtimes with Kubernetes CRI.

CRI-O is an implementation of the cri
to enable using container
runtimes that are compatible with the Open Container Initiative (OCI)
[runtime spec](https://www.github.com/opencontainers/runtime-spec).

Deploying CRI-O allows Kubernetes to use any OCI-compliant runtime as the container
runtime for running Pods, and to fetch
OCI container images from remote registries.