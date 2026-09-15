# EventSource

`apiVersion: v1`

`import "k8s.io/api/core/v1"`

## EventSource {#EventSource}

EventSource contains information for an event.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>component</code><br/><em>string</em></td>
      <td>Component from which the event is generated.</td>
    </tr>
    <tr>
      <td><code>host</code><br/><em>string</em></td>
      <td>Node name on which the event is generated.</td>
    </tr>
  </tbody>
</table>