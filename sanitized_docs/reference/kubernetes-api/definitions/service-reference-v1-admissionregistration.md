# ServiceReference

`apiVersion: admissionregistration.k8s.io/v1`

`import "k8s.io/api/admissionregistration/v1"`

## ServiceReference {#ServiceReference}

ServiceReference holds a reference to Service.legacy.k8s.io

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>name</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>name is the name of the service. Required</td>
    </tr>
    <tr>
      <td><code>namespace</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td>namespace is the namespace of the service. Required</td>
    </tr>
    <tr>
      <td><code>path</code><br/><em>string</em></td>
      <td>path is an optional URL path which will be sent in any request to this service.</td>
    </tr>
    <tr>
      <td><code>port</code><br/><em>integer</em></td>
      <td>port is the port on the service that hosts the webhook. Default to 443 for backward compatibility. `port` should be a valid port number (1-65535, inclusive).</td>
    </tr>
  </tbody>
</table>