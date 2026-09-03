## REMOVED Requirements

Every requirement of this capability is removed. One chart contract now covers every
product, stated in `ssh-chart-contract`; a capability describing one of two profiles has
nothing left to describe.

### Requirement: A product declares one access profile, and a deployment renders only that one

**Reason**: A product declares a session root, not a profile, and one sidecar serves every declaration. Stated by `ssh-chart-contract` § *A product declares a session root, or declares no SSH access*, which also keeps the declaration out of the tenant-influenced channel.

**Migration**: `custom` declares an application-container session root; the six products that declared `sftp` declare a volume session root.

### Requirement: SSH resources are rendered on the declared profile, not on the presence of a PVC

**Reason**: Stated by `ssh-chart-contract` § *A product declares a session root, or declares no SSH access*, which requires the declaration in both directions — a volume does not select a session root, and its absence does not select one either.

**Migration**: None. A product with a volume and no declaration renders nothing, as does a product with neither.

### Requirement: The dev profile runs the platform's SSH sidecar image at a pinned version

**Reason**: Stated by `ssh-chart-contract` § *The chart runs the platform's sidecar image at a pinned version*, which applies to every deployment because there is one image.

**Migration**: The six curated charts move from `atmoz/sftp` to the platform image at the pinned tag their `values.yaml` already carries for the sidecar.

### Requirement: The pod grants the sidecar exactly the facilities it needs, and no more

**Reason**: Stated by `ssh-chart-contract` § *An application root requires a shared process namespace and nothing more*, which attaches the requirement to the session root that needs it rather than to a profile.

**Migration**: None. A volume-rooted pod does not share a process namespace and does not need to.

### Requirement: The chart supplies every runtime input the sidecar requires

**Reason**: Stated by `ssh-chart-contract` § *The chart supplies every runtime input the sidecar requires*, with the session root added to the required set.

**Migration**: Charts pass the session root alongside the inputs they already pass.

### Requirement: The forward allowlist admits the deployment's database and nothing else by default

**Reason**: Stated unchanged by `ssh-chart-contract` § *The forward allowlist admits the deployment's database and nothing else by default*.

**Migration**: None.

### Requirement: The profile does not require its product to have a database

**Reason**: Stated by `ssh-chart-contract` § *The chart supplies every runtime input the sidecar requires*, which makes the database inputs conditional, and by `ssh-sidecar-image`, which declines the database tooling by name when they are absent.

**Migration**: None.

### Requirement: The dev profile offers no SFTP subsystem and mounts no volume

**Reason**: Every deployment serves file transfer, from the sidecar's own tooling, rooted at its declared session root. An application-rooted deployment still mounts no tenant volume, which is stated by `ssh-chart-contract` § *An application root requires a shared process namespace and nothing more* and by `ssh-sidecar-image` § *File transfer is served by the image's own tooling*.

**Migration**: `scp` and `sftp` begin working against an application-rooted deployment whose image carries no file-transfer helper of its own. Nothing that worked stops working.

### Requirement: Both profiles present the same Service to the edge

**Reason**: Stated by `ssh-chart-contract` § *Every deployment presents the same Service to the edge*, which no longer has two cases to reconcile.

**Migration**: None.
