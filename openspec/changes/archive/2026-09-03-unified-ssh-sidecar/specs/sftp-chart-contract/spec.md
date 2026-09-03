## REMOVED Requirements

Every requirement of this capability is removed. One chart contract now covers every
product, stated in `ssh-chart-contract`; a second contract describing one of two profiles
has nothing left to describe.

### Requirement: SFTP sidecar with read-only mounts of exposable PVCs

**Reason**: Stated by `ssh-chart-contract` § *A volume root is mounted read-only and does not depend on the application*, without reference to a particular SFTP implementation and without the per-product uid the mounts previously had to match.

**Migration**: A curated product's chart declares a volume session root and passes the same mounts. `internalUid`/`internalGid` are dropped: sessions run as root and the read-only mount is what constrains them.

### Requirement: Sessions are SFTP-only, read-only, with no shell

**Reason**: Stated by `ssh-chart-contract` § *The session root decides what a session may do* and § *A volume root is mounted read-only*, where the restriction follows from the declared session root rather than from a server that can do nothing else.

**Migration**: None for a user. A volume-rooted session serves file transfer and refuses a shell, a remote command and the database tooling by name.

### Requirement: File access survives an unhealthy application container

**Reason**: Stated by `ssh-chart-contract` § *A volume root is mounted read-only and does not depend on the application*.

**Migration**: None. The sidecar mounts the volume itself and reaches nothing through the application container, so the property is unchanged.

### Requirement: The SFTP sidecar is liveness-probed

**Reason**: Stated by `ssh-chart-contract` § *The sidecar is liveness-probed independently of the application*, which applies to every deployment rather than to one profile's.

**Migration**: None.

### Requirement: Products render SSH resources only when they declare an access profile

**Reason**: Stated by `ssh-chart-contract` § *A product declares a session root, or declares no SSH access*, in terms of the one declaration a product now makes.

**Migration**: A product that declared a profile declares a session root instead. A product that declared no profile continues to render nothing.

### Requirement: Per-deployment Service targets the sidecar

**Reason**: Stated by `ssh-chart-contract` § *Every deployment presents the same Service to the edge*.

**Migration**: None. The Service's name, port, selector semantics and `publishNotReadyAddresses` are unchanged, which is why no deployment becomes unroutable.

### Requirement: Per-deployment credentials Secret carries no password

**Reason**: No credentials Secret is rendered. The sidecar takes every input as an environment variable and writes its own `authorized_keys` and configuration at startup, so there is no user list, trusted-key file or startup script for an object to carry. What the requirement protected — no password, no private key, no user's public key in a tenant namespace — is stated by `ssh-chart-contract` § *The tenant's namespace holds no credential for this feature*.

**Migration**: The Secret and the sshd-init ConfigMap are removed by the Helm upgrade that stops rendering them. Nothing reads them.
