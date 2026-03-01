# k8s Development VM Provisioning

Script: `k8s/provision-dev-k3s-vm.sh`

This script provisions a new Proxmox VM for k3s development by cloning a prebuilt Ubuntu cloud-image template, waits for SSH, installs k3s, writes a local kubeconfig, and runs `kubectl get nodes`.

## Environment File

The script automatically loads `k8s/.env` if it exists.

- You can use a different file path with `K8S_ENV_FILE=/path/to/file.env`.
- The file is sourced by bash, so treat it as trusted code.

## Why this flow

Ubuntu live-server ISO install is typically interactive unless you wire autoinstall seed media and boot args. For repeated dev provisioning, cloning a cloud-image template is faster and fully non-interactive.

## One-time Proxmox Template Setup

Run these on your Proxmox node (example uses VMID `9000`):

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img -O /var/lib/vz/template/iso/noble-server-cloudimg-amd64.img

qm create 9000 --name ubuntu-2404-cloud-template --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 9000 /var/lib/vz/template/iso/noble-server-cloudimg-amd64.img local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm template 9000
```

Important: IP detection in the provisioning script uses the Proxmox QEMU guest-agent API for the new VM.
Make sure your template image includes `qemu-guest-agent` and that the service starts in the guest.

## Required Tools

- `curl`
- `jq`
- `ssh`
- `kubectl`

## Auth Options (choose one)

1. API token:

```bash
export PROXMOX_API_TOKEN='user@pve!tokenid=secret'
```

2. Username/password:

```bash
export PROXMOX_USER='root@pam'
export PROXMOX_PASSWORD='...'
```

## Typical Run

```bash
export PROXMOX_HOST='192.168.0.15'
# Optional if your Proxmox cluster has exactly 1 node:
# export PROXMOX_NODE='pve-node-name'
export TEMPLATE_VM_ID='9000'
# or: export TEMPLATE_VM_NAME='ubuntu-2404-cloud-template'

export SSH_USER='ubuntu'
export SSH_PUBLIC_KEY_PATH="$HOME/.ssh/id_ed25519.pub"
export SSH_PRIVATE_KEY_PATH="$HOME/.ssh/id_ed25519"

./k8s/provision-dev-k3s-vm.sh
```

## Dry Run

Validate auth, node/template resolution, key paths, and next VMID without creating anything:

```bash
./k8s/provision-dev-k3s-vm.sh --dry-run
```

## Key Defaults

- RAM: `8192` MB
- Disk: `30` GB on `local-lvm` (`scsi0` resize)
- DNS override: `192.168.0.9`
- Network: DHCP (`ipconfig0=ip=dhcp`)
- Cloud-init drive storage: `local-lvm`
- Clone type: full clone (`FULL_CLONE=1`)
- VM IP lookup: Proxmox guest-agent API for the provisioned VM

## Output Files

- Last detected VM IP: `k8s/last_vm_ip.txt`
- Generated kubeconfig: `k8s/kubeconfigs/<vm-name>-<vmid>.yaml`


# Onboarding new Helm Charts

### Use local Helm repo:

To onboard a new Helm chart (e.g. Nextcloud -- https://github.com/nextcloud/helm/tree/main/charts/nextcloud):

```bash
helm repo add nextcloud https://nextcloud.github.io/helm/
helm repo update
# Now see all the versions available:
helm search repo nextcloud/nextcloud --versions
```

Then to manually test install the chart:

```bash
helm upgrade --install nextcloud-test nextcloud/nextcloud --namespace nextcloud-test --create-namespace --version 8.9.1 \
    --set ingress.enabled=true \
    --set ingress.className=traefik \
    --set phpClientHttpsFix.enabled=true \
    --set phpClientHttpsFix.protocol=https \
    --set nextcloud.host=nextcloud-test.app.deprutser.be
```

Visit https://nextcloud-test.app.deprutser.be/ and login with `admin/changeme`.
Afterward, clean up with `helm uninstall nextcloud-test --namespace nextcloud-test`

### Point directly to the online chart release archive

Instead of adding the product's helm repo locally, you can point to the online chart release archive.
E.g. https://github.com/nextcloud/helm/releases/download/nextcloud-8.9.1/nextcloud-8.9.1.tgz

```bash
helm upgrade --install nextcloud-test https://github.com/nextcloud/helm/releases/download/nextcloud-8.9.1/nextcloud-8.9.1.tgz --namespace nextcloud-test --create-namespace --version 8.9.1 \
    --set ingress.enabled=true \
    --set ingress.className=traefik \
    --set phpClientHttpsFix.enabled=true \
    --set phpClientHttpsFix.protocol=https \
    --set persistence.enabled=true \
    --set persistence.nextcloudData.enabled=true \
    --set nextcloud.host=nextcloud-test.app.deprutser.be
```

## Onboarding: Create product and template

Then in the admin UI, create a product and template for the new chart. The template should use the following:

### Default values

```json
{
    "ingress": {
        "enabled": true,
        "className": "traefik"
    },
    "phpClientHttpsFix": {
        "enabled": true,
        "protocol": "https"
    }
}
```

### Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "nextcloud": {
      "type": "object",
      "properties": {
        "host": {
          "title": "domainname",
          "type": "string",
          "minLength": 1,
          "maxLength": 64,
          "pattern": "^((?!-)(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]?\\.)+(xn--)?[a-z0-9-]{2,}$",
          "description": "The domainname for your Nextcloud instance"
        }
      },
      "required": ["host"],
      "additionalProperties": false
    }
  },
  "required": ["nextcloud"],
  "additionalProperties": false
}
```

Note: additional user-defined values could be added from: https://github.com/nextcloud/helm/tree/main/charts/nextcloud#configuration
