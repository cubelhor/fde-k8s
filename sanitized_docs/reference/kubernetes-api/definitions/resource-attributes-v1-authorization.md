# ResourceAttributes

`apiVersion: authorization.k8s.io/v1`

`import "k8s.io/api/authorization/v1"`

## ResourceAttributes {#ResourceAttributes}

ResourceAttributes includes the authorization attributes available for resource requests to the Authorizer interface

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>fieldSelector</code><br/><em><a href="https://kubernetes.io/docs/field-selector-attributes-v1-authorization#FieldSelectorAttributes">FieldSelectorAttributes</a></em></td>
      <td>fieldSelector describes the limitation on access based on field.  It can only limit access, not broaden it.</td>
    </tr>
    <tr>
      <td><code>group</code><br/><em>string</em></td>
      <td>group is the API Group of the Resource.  "*" means all.</td>
    </tr>
    <tr>
      <td><code>labelSelector</code><br/><em><a href="https://kubernetes.io/docs/label-selector-attributes-v1-authorization#LabelSelectorAttributes">LabelSelectorAttributes</a></em></td>
      <td>labelSelector describes the limitation on access based on labels.  It can only limit access, not broaden it.</td>
    </tr>
    <tr>
      <td><code>name</code><br/><em>string</em></td>
      <td>name is the name of the resource being requested for a "get" or deleted for a "delete". "" (empty) means all.</td>
    </tr>
    <tr>
      <td><code>namespace</code><br/><em>string</em></td>
      <td>namespace is the namespace of the action being requested.  Currently, there is no distinction between no namespace and all namespaces "" (empty) is defaulted for LocalSubjectAccessReviews "" (empty) is empty for cluster-scoped resources "" (empty) means "all" for namespace scoped resources from a SubjectAccessReview or SelfSubjectAccessReview</td>
    </tr>
    <tr>
      <td><code>resource</code><br/><em>string</em></td>
      <td>resource is one of the existing resource types.  "*" means all.</td>
    </tr>
    <tr>
      <td><code>subresource</code><br/><em>string</em></td>
      <td>subresource is one of the existing resource types.  "" means none.</td>
    </tr>
    <tr>
      <td><code>verb</code><br/><em>string</em></td>
      <td>verb is a kubernetes resource API verb, like: get, list, watch, create, update, delete, proxy.  "*" means all.</td>
    </tr>
    <tr>
      <td><code>version</code><br/><em>string</em></td>
      <td>version is the API Version of the Resource.  "*" means all.</td>
    </tr>
  </tbody>
</table>