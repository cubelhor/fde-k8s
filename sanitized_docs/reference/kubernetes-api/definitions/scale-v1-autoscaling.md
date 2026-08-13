# Scale

`apiVersion: autoscaling/v1`

`import "k8s.io/api/autoscaling/v1"`

## Scale {#Scale}

Scale represents a scaling request for a resource.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>apiVersion</code><br/><em>string</em></td>
      <td>APIVersion defines the versioned schema of this representation of an object. Servers should convert recognized schemas to the latest internal value, and may reject unrecognized values. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#resources</td>
    </tr>
    <tr>
      <td><code>kind</code><br/><em>string</em></td>
      <td>Kind is a string value representing the REST resource this object represents. Servers may infer this from the endpoint the client submits requests to. Cannot be updated. In CamelCase. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#types-kinds</td>
    </tr>
    <tr>
      <td><code>metadata</code><br/><em><a href="https://kubernetes.io/docs/object-meta-v1-meta#ObjectMeta">ObjectMeta</a></em></td>
      <td>Standard object metadata; More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#metadata.</td>
    </tr>
    <tr>
      <td><code>spec</code><br/><em><a href="https://kubernetes.io/docs/#ScaleSpec">ScaleSpec</a></em></td>
      <td>spec defines the behavior of the scale. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#spec-and-status.</td>
    </tr>
    <tr>
      <td><code>status</code><br/><em><a href="https://kubernetes.io/docs/#ScaleStatus">ScaleStatus</a></em></td>
      <td>status is the current status of the scale. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#spec-and-status. Read-only.</td>
    </tr>
  </tbody>
</table>

## ScaleSpec {#ScaleSpec}

ScaleSpec describes the attributes of a scale subresource.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>replicas</code><br/><em>integer</em></td>
      <td>replicas is the desired number of instances for the scaled object.</td>
    </tr>
  </tbody>
</table>

## ScaleStatus {#ScaleStatus}

ScaleStatus represents the current status of a scale subresource.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>replicas</code>&nbsp;<strong>*</strong><br/><em>integer</em></td>
      <td>replicas is the actual number of observed instances of the scaled object.</td>
    </tr>
    <tr>
      <td><code>selector</code><br/><em>string</em></td>
      <td>selector is the label query over pods that should match the replicas count. This is same as the label selector but in the string format to avoid introspection by clients. The string will be in the same format as the query-param syntax. More info about label selectors: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/</td>
    </tr>
  </tbody>
</table>