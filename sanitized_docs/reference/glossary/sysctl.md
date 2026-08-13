# sysctl

`sysctl` is a semi-standardized interface for reading or changing the
 attributes of the running Unix kernel.

On Unix-like systems, `sysctl` is both the name of the tool that administrators
use to view and modify these settings, and also the system call that the tool
uses.

Container runtimes and
network plugins may rely on `sysctl` values being set a certain way.