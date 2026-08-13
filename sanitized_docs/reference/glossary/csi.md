# Container Storage Interface (CSI)

The Container Storage Interface (CSI) defines a standard interface to expose storage systems to containers.

 

CSI allows vendors to create custom storage plugins for Kubernetes without adding them to the Kubernetes repository (out-of-tree plugins). To use a CSI driver from a storage provider, you must first [deploy it to your cluster](https://kubernetes-csi.github.io/docs/deploying.html). You will then be able to create a Storage Class that uses that CSI driver.

* [CSI in the Kubernetes documentation](/docs/concepts/storage/volumes/#csi)
* [List of available CSI drivers](https://kubernetes-csi.github.io/docs/drivers.html)