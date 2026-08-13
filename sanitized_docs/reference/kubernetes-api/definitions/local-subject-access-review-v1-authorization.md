# LocalSubjectAccessReview

`apiVersion: authorization.k8s.io/v1`

`import "k8s.io/api/authorization/v1"`

## LocalSubjectAccessReview {#LocalSubjectAccessReview}

LocalSubjectAccessReview checks whether or not a user or group can perform an action in a given namespace. Having a namespace scoped resource makes it much easier to grant namespace scoped policy that includes permissions checking.

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
      <td>metadata is the standard list metadata. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#metadata</td>
    </tr>
    <tr>
      <td><code>spec</code>&nbsp;<strong>*</strong><br/><em>SubjectAccessReviewSpec</em></td>
      <td>spec holds information about the request being evaluated.  spec.namespace must be equal to the namespace you made the request against.  If empty, it is defaulted.</td>
    </tr>
    <tr>
      <td><code>status</code><br/><em>SubjectAccessReviewStatus</em></td>
      <td>status is filled in by the server and indicates whether the request is allowed or not</td>
    </tr>
  </tbody>
</table>