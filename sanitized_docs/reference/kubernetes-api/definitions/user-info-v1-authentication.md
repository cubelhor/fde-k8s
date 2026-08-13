# UserInfo

`apiVersion: authentication.k8s.io/v1`

`import "k8s.io/api/authentication/v1"`

## UserInfo {#UserInfo}

UserInfo holds the information about the user needed to implement the user.Info interface.

<hr>

<table>
  <thead><tr><th>Field</th><th>Description</th></tr></thead>
  <tbody>
    <tr>
      <td><code>extra</code><br/><em>object</em></td>
      <td>extra is any additional information provided by the authenticator.</td>
    </tr>
    <tr>
      <td><code>groups</code><br/><em>string array</em></td>
      <td>groups is the names of groups this user is a part of.</td>
    </tr>
    <tr>
      <td><code>uid</code><br/><em>string</em></td>
      <td>uid is a unique value that identifies this user across time. If this user is deleted and another user by the same name is added, they will have different UIDs.</td>
    </tr>
    <tr>
      <td><code>username</code><br/><em>string</em></td>
      <td>username is the name that uniquely identifies this user among all active users.</td>
    </tr>
  </tbody>
</table>