# Drain

The process of safely evicting Pods from a Node to prepare it for maintenance or removal from a cluster.

The `kubectl drain` command is used to mark a Node as going out of service. 
When executed, it evicts all Pods from the Node. 
If an eviction request is temporarily rejected, `kubectl drain` retries until all Pods are terminated or a configurable timeout is reached.