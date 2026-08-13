# Init Container

One or more initialization containers that must run to completion before any app containers run.

 

Initialization (init) containers are like regular app containers, with one difference: init containers must run to completion before any app containers can start. Init containers run in series: each init container must run to completion before the next init container begins.

Unlike sidecar containers, init containers do not remain running after Pod startup.

For more information, read [init containers](/docs/concepts/workloads/pods/init-containers/).