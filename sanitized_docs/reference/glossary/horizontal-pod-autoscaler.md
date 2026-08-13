# Horizontal Pod Autoscaler

An object that automatically scales the number of pod replicas,
based on targeted resource utilization or custom metric targets.

 

HorizontalPodAutoscaler (HPA) is typically used with Deployments, or ReplicaSets. It cannot be applied to objects that cannot be scaled, for example DaemonSets.