# ServiceAccount

Provides an identity for processes that run in a Pod.

 

When processes inside Pods access the cluster, they are authenticated by the API server as a particular service account, for example, `default`. When you create a Pod, if you do not specify a service account, it is automatically assigned the default service account in the same Namespace.