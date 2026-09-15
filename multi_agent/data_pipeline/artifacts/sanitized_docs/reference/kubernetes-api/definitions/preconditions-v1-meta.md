# Preconditions

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## Preconditions {#Preconditions}

Preconditions must be fulfilled before an operation (update, delete, etc.) is carried out.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>resourceVersion</code><br/><em>string</em></td>
      <td>Specifies the target ResourceVersion</td>
    </tr>
    <tr>
      <td><code>uid</code><br/><em>string</em></td>
      <td>Specifies the target UID.</td>
    </tr>
  </tbody>
</table>