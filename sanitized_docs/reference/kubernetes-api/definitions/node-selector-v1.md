# NodeSelector

`apiVersion: v1`

`import "k8s.io/api/core/v1"`

## NodeSelector {#NodeSelector}

A node selector represents the union of the results of one or more label queries over a set of nodes; that is, it represents the OR of the selectors represented by the node selector terms.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>nodeSelectorTerms</code>&nbsp;<strong>*</strong><br/><em><a href="https://kubernetes.io/docs/node-selector-term-v1#NodeSelectorTerm">NodeSelectorTerm array</a></em></td>
      <td>Required. A list of node selector terms. The terms are ORed.</td>
    </tr>
  </tbody>
</table>