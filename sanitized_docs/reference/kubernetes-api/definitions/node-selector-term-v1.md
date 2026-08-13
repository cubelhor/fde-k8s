# NodeSelectorTerm

`apiVersion: v1`

`import "k8s.io/api/core/v1"`

## NodeSelectorTerm {#NodeSelectorTerm}

A null or empty node selector term matches no objects. The requirements of them are ANDed. The TopologySelectorTerm type implements a subset of the NodeSelectorTerm.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>matchExpressions</code><br/><em><a href="https://kubernetes.io/docs/../resource/resource-slice-v1#NodeSelectorRequirement">NodeSelectorRequirement array</a></em></td>
      <td>A list of node selector requirements by node's labels.</td>
    </tr>
    <tr>
      <td><code>matchFields</code><br/><em><a href="https://kubernetes.io/docs/../resource/resource-slice-v1#NodeSelectorRequirement">NodeSelectorRequirement array</a></em></td>
      <td>A list of node selector requirements by node's fields.</td>
    </tr>
  </tbody>
</table>