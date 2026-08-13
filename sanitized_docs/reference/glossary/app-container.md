# App Container

Application containers (or app containers) are the containers in a pod that are started after any init containers have completed.

An init container lets you separate initialization details that are important for the overall 
workload, and that don't need to keep running
once the application container has started.
If a pod doesn't have any init containers configured, all the containers in that pod are app containers.