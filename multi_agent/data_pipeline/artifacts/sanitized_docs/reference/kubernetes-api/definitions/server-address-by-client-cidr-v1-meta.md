# ServerAddressByClientCIDR

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## ServerAddressByClientCIDR {#ServerAddressByClientCIDR}

ServerAddressByClientCIDR helps the client to determine the server address that they should use, depending on the clientCIDR that they match.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>clientCIDR</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>The CIDR with which clients can match their IP to figure out the server address that they should use.</td>
    </tr>
    <tr>
      <td><code>serverAddress</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>Address of this server, suitable for a client that matches the above CIDR. This can be a hostname, hostname:port, IP or IP:port.</td>
    </tr>
  </tbody>
</table>