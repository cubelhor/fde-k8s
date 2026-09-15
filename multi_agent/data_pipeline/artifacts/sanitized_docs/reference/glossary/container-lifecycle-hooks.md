# Container Lifecycle Hooks

The lifecycle hooks expose events in the Container management lifecycle and let the user run code when the events occur.

Two hooks are exposed to Containers: PostStart which executes immediately after a container is created and PreStop which is blocking and is called immediately before a container is terminated.