# Dynamic Volume Provisioning

Allows users to request automatic creation of storage  Volumes.

 

Dynamic provisioning eliminates the need for cluster administrators to pre-provision storage. Instead, it automatically provisions storage by user request. Dynamic volume provisioning is based on an API object, StorageClass, referring to a Volume Plugin that provisions a Volume and the set of parameters to pass to the Volume Plugin.