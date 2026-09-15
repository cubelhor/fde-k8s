# StaleControllerConsistencyDaemonSet

Enables behavior within the DaemonSet controller to ensure that prior writes to
the API server are observed before proceeding with additional reconciliation for the same DaemonSet.
This is to prevent stale cache from causing incorrect or spurious updates to the DaemonSet.