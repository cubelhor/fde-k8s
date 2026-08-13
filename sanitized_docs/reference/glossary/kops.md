# kOps (Kubernetes Operations)

`kOps` will not only help you create, destroy, upgrade and maintain production-grade, highly available, Kubernetes cluster, but it will also provision the necessary cloud infrastructure.

 

> **Note:** AWS (Amazon Web Services) is currently officially supported, with DigitalOcean, GCE and OpenStack in beta support, and Azure in alpha.

`kOps` is an automated provisioning system:
  * Fully automated installation
  * Uses DNS to identify clusters
  * Self-healing: everything runs in Auto-Scaling Groups
  * Multiple OS support (Amazon Linux, Debian, Flatcar, RHEL, Rocky and Ubuntu)
  * High-Availability support
  * Can directly provision, or generate terraform manifests