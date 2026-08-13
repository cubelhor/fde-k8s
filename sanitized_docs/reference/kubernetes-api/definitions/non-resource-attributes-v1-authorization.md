# NonResourceAttributes

`apiVersion: authorization.k8s.io/v1`

`import "k8s.io/api/authorization/v1"`

## NonResourceAttributes {#NonResourceAttributes}

NonResourceAttributes includes the authorization attributes available for non-resource requests to the Authorizer interface

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>path</code><br/><em>string</em></td>
      <td>path is the URL path of the request</td>
    </tr>
    <tr>
      <td><code>verb</code><br/><em>string</em></td>
      <td>verb is the standard HTTP verb</td>
    </tr>
  </tbody>
</table>