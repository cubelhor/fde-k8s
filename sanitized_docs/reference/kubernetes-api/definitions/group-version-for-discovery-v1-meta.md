# GroupVersionForDiscovery

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## GroupVersionForDiscovery {#GroupVersionForDiscovery}

GroupVersion contains the &#34;group/version&#34; and &#34;version&#34; string of a version. It is made a struct to keep extensibility.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>groupVersion</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>groupVersion specifies the API group and version in the form "group/version"</td>
    </tr>
    <tr>
      <td><code>version</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>version specifies the version in the form of "version". This is to save the clients the trouble of splitting the GroupVersion.</td>
    </tr>
  </tbody>
</table>