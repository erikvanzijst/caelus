Create the initial cloudinit VM template:

```
# 1) Pick an unused VMID (example uses 9000)
qm create 9000 --name ubuntu-2404-cloud-template

# 2) Import the cloud image disk into local-lvm
qm importdisk 9000 /var/lib/vz/template/iso/noble-server-cloudimg-amd64.img local-lvm

# 3) Attach imported disk as boot disk
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0

# 4) Add cloud-init drive
qm set 9000 --ide2 local-lvm:cloudinit

# 5) Set boot + console + guest agent
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm set 9000 --net0 virtio,bridge=vmbr0
qm set 9000 --ipconfig0 ip=dhcp

# 6) Convert to template
qm template 9000
```qm create 9000 --name ubuntu-2404-cloud-template

# 2) Import the cloud image disk into local-lvm
qm importdisk 9000 /var/lib/vz/template/iso/noble-server-cloudimg-amd64.img local-lvm

# 3) Attach imported disk as boot disk
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0

# 4) Add cloud-init drive
qm set 9000 --ide2 local-lvm:cloudinit

# 5) Set boot + console + guest agent
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm set 9000 --net0 virtio,bridge=vmbr0
qm set 9000 --ipconfig0 ip=dhcp
qm set 9000 --ciuser=ubuntu
qm set 9000 --sshkeys=./id_ed25519.pub


# Boot VM, ssh into it and install guest agent:
apt install -y qemu-guest-agent

# Shut down and convert to template:
qm template 9000
```

Create a user and role for the provisioner:
```
pveum user add caelus@pve --password 'CHANGE_ME'
pveum role add caelus-provisioner --privs "VM.Allocate VM.Config.CDROM VM.Clone VM.Audit VM.PowerMgmt VM.Config.CPU VM.Config.Memory VM.Config.Network VM.Config.Options VM.Config.Disk VM.Config.Cloudinit VM.GuestAgent.Audit Datastore.Audit Datastore.AllocateSpace Sys.Audit SDN.Use"

# grant role on root path (applies to VMs, node, storage)
pveum aclmod / -user caelus@pam -role caelus-provisioner

# API token for script (recommended):
pveum user token add caelus@pam caelus --privsep 0

#Then set in your .env:
PROXMOX_API_TOKEN='caelus@pam!caelus=YOUR_TOKEN_SECRET'
```
