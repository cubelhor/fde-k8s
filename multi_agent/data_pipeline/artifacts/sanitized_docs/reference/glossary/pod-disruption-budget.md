# Pod Disruption Budget

A [Pod Disruption Budget](/docs/concepts/workloads/pods/disruptions/) allows an 
 application owner to create an object for a replicated application, that ensures 
 a certain number or percentage of Pods
 with an assigned label will not be voluntarily evicted at any point in time.

 

Involuntary disruptions cannot be prevented by PDBs; however they 
do count against the budget.