# Control Plane

The container orchestration layer that exposes the API and interfaces to define, deploy, and manage the lifecycle of containers.

  
 
 This layer is composed by many different components, such as (but not restricted to):

 * etcd
 * API Server
 * Scheduler
 * Controller Manager
 * Cloud Controller Manager

 These components can be run as traditional operating system services (daemons) or as containers. The hosts running these components were historically called masters.