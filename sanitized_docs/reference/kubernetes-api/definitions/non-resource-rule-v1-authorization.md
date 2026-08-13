# NonResourceRule

`apiVersion: authorization.k8s.io/v1`

`import "k8s.io/api/authorization/v1"`

## NonResourceRule {#NonResourceRule}

NonResourceRule holds information that describes a rule for the non-resource

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>nonResourceURLs</code><br/><em>string array</em></td>
      <td>nonResourceURLs is a set of partial urls that a user should have access to.  *s are allowed, but only as the full, final step in the path.  "*" means all.</td>
    </tr>
    <tr>
      <td><code>verbs</code>&nbsp;<strong>*</strong><br/><em>string array</em></td>
      <td>verbs is a list of kubernetes non-resource API verbs, like: get, post, put, delete, patch, head, options.  "*" means all.</td>
    </tr>
  </tbody>
</table>