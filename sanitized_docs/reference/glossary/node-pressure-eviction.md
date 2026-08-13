# Node-pressure eviction

Node-pressure eviction is the process by which the kubelet proactively terminates
pods to reclaim resource
on nodes.

The kubelet monitors resources like CPU, memory, disk space, and filesystem 
inodes on your cluster's nodes. When one or more of these resources reach
specific consumption levels, the kubelet can proactively fail one or more pods
on the node to reclaim resources and prevent starvation. 

Node-pressure eviction is not the same as [API-initiated eviction](/docs/concepts/scheduling-eviction/api-eviction/).