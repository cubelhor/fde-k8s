# SubjectAccessReview

`apiVersion: authorization.k8s.io/v1`

`import "k8s.io/api/authorization/v1"`

## SubjectAccessReview {#SubjectAccessReview}

SubjectAccessReview checks whether or not a user or group can perform an action.

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
      <td><code>spec</code>&nbsp;<strong>*</strong><br/><em><a href="https://kubernetes.io/docs/#SubjectAccessReviewSpec">SubjectAccessReviewSpec</a></em></td>
      <td>spec holds information about the request being evaluated</td>
    </tr>
    <tr>
      <td><code>status</code><br/><em><a href="https://kubernetes.io/docs/#SubjectAccessReviewStatus">SubjectAccessReviewStatus</a></em></td>
      <td>status is filled in by the server and indicates whether the request is allowed or not</td>
    </tr>
  </tbody>
</table>

## SubjectAccessReviewSpec {#SubjectAccessReviewSpec}

SubjectAccessReviewSpec is a description of the access request.  Exactly one of resourceAttributes and nonResourceAttributes must be set

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>extra</code><br/><em>object</em></td>
      <td>extra corresponds to the user.Info.GetExtra() method from the authenticator.  Since that is input to the authorizer it needs a reflection here.</td>
    </tr>
    <tr>
      <td><code>groups</code><br/><em>string array</em></td>
      <td>groups is the groups you're testing for.</td>
    </tr>
    <tr>
      <td><code>nonResourceAttributes</code><br/><em><a href="https://kubernetes.io/docs/non-resource-attributes-v1-authorization#NonResourceAttributes">NonResourceAttributes</a></em></td>
      <td>nonResourceAttributes describes information for a non-resource access request</td>
    </tr>
    <tr>
      <td><code>resourceAttributes</code><br/><em><a href="https://kubernetes.io/docs/resource-attributes-v1-authorization#ResourceAttributes">ResourceAttributes</a></em></td>
      <td>resourceAttributes describes information for a resource access request</td>
    </tr>
    <tr>
      <td><code>uid</code><br/><em>string</em></td>
      <td>uid information about the requesting user.</td>
    </tr>
    <tr>
      <td><code>user</code><br/><em>string</em></td>
      <td>user is the user you're testing for. If you specify "User" but not "Groups", then is it interpreted as "What if User were not a member of any groups</td>
    </tr>
  </tbody>
</table>

## SubjectAccessReviewStatus {#SubjectAccessReviewStatus}

SubjectAccessReviewStatus

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>allowed</code>&nbsp;<strong>*</strong><br/><em>boolean</em></td>
      <td>allowed is required. True if the action would be allowed, false otherwise.</td>
    </tr>
    <tr>
      <td><code>denied</code><br/><em>boolean</em></td>
      <td>denied is optional. True if the action would be denied, otherwise false. If both allowed is false and denied is false, then the authorizer has no opinion on whether to authorize the action. Denied may not be true if Allowed is true.</td>
    </tr>
    <tr>
      <td><code>evaluationError</code><br/><em>string</em></td>
      <td>evaluationError is an indication that some error occurred during the authorization check. It is entirely possible to get an error and be able to continue determine authorization status in spite of it. For instance, RBAC can be missing a role, but enough roles are still present and bound to reason about the request.</td>
    </tr>
    <tr>
      <td><code>reason</code><br/><em>string</em></td>
      <td>reason is optional.  It indicates why a request was allowed or denied.</td>
    </tr>
  </tbody>
</table>