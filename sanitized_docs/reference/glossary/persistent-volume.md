# Persistent Volume

An API object that represents a piece of storage in the cluster. Representation of as a general, pluggable storage
resource that can persist beyond the lifecycle of any
individual Pod.

 

PersistentVolumes (PVs) provide an API that abstracts details of how storage is provided from how it is consumed.
PVs are used directly in scenarios where storage can be created ahead of time (static provisioning).
For scenarios that require on-demand storage (dynamic provisioning), PersistentVolumeClaims (PVCs) are used instead.