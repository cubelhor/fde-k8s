# ShardInfo

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## ShardInfo {#ShardInfo}

ShardInfo describes the shard selector that was applied to produce a list response. Its presence on a list response indicates the list is a filtered subset.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>selector</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>selector is the shard selector string from the request, echoed back so clients can verify which shard they received and merge responses from multiple shards.</td>
    </tr>
  </tbody>
</table>