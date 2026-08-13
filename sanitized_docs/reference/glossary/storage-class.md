# Storage Class

A StorageClass provides a way for administrators to describe different available storage types.

 

StorageClasses can map to quality-of-service levels, backup policies, or to arbitrary policies determined by cluster administrators. Each StorageClass contains the fields `provisioner`, `parameters`, and `reclaimPolicy`, which are used when a Persistent Volume belonging to the class needs to be dynamically provisioned. Users can request a particular class using the name of a StorageClass object.