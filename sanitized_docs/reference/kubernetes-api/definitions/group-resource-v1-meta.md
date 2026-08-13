# GroupResource

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## GroupResource {#GroupResource}

GroupResource specifies a Group and a Resource, but does not force a version.  This is useful for identifying concepts during lookup stages without having partially valid types

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>group</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td></td>
    </tr>
    <tr>
      <td><code>resource</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td></td>
    </tr>
  </tbody>
</table>