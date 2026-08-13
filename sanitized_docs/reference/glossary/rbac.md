# RBAC (Role-Based Access Control)

Manages authorization decisions, allowing admins to dynamically configure access policies through the Kubernetes API.

 

RBAC utilizes four kinds of Kubernetes objects:

Role
: Defines permission rules in a specific namespace.

ClusterRole
: Defines permission rules cluster-wide.

RoleBinding
: Grants the permissions defined in a role to a set of users in a specific namespace.

ClusterRoleBinding
: Grants the permissions defined in a role to a set of users cluster-wide.

For more information, see [RBAC](/docs/reference/access-authn-authz/rbac/).