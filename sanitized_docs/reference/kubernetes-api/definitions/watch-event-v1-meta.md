# WatchEvent

`apiVersion: meta/v1`

`import "k8s.io/apimachinery/pkg/apis/meta/v1"`

## WatchEvent {#WatchEvent}

Event represents a single event to a watched resource.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>object</code>&nbsp;<strong>*</strong><br/><em></em></td>
      <td>Object is:  * If Type is Added or Modified: the new state of the object.  * If Type is Deleted: the state of the object immediately before deletion.  * If Type is Error: *Status is recommended; other types may make sense    depending on context.</td>
    </tr>
    <tr>
      <td><code>type</code>&nbsp;<strong>*</strong><br/><em>string</em></td>
      <td></td>
    </tr>
  </tbody>
</table>