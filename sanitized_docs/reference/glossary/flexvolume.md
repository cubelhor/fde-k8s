# FlexVolume

FlexVolume is a deprecated interface for creating out-of-tree volume plugins. The Container Storage Interface is a newer interface that addresses several problems with FlexVolume.

 

FlexVolumes enable users to write their own drivers and add support for their volumes in Kubernetes. FlexVolume driver binaries and dependencies must be installed on host machines. This requires root access. The Storage SIG suggests implementing a CSI driver if possible since it addresses the limitations with FlexVolumes.

* [FlexVolume in the Kubernetes documentation](/docs/concepts/storage/volumes/#flexvolume)
* [More information on FlexVolumes](https://github.com/kubernetes/community/blob/main/contributors/devel/sig-storage/flexvolume.md)
* [Volume Plugin FAQ for Storage Vendors](https://github.com/kubernetes/community/blob/main/sig-storage/volume-plugin-faq.md)