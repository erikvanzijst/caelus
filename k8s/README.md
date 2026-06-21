# k3s Cluster Host

The k3s cluster runs inside a single long-lived **libvirt/KVM virtual machine** named
`caelus`, hosted on a Ubuntu 24.04 LTS home server.


## Managing the VM

```bash
sudo virsh list --all                 # state
sudo virsh dominfo caelus             # specs, autostart status
sudo virsh start caelus               # start (autostart is enabled by default)
sudo virsh shutdown caelus            # graceful ACPI shutdown
sudo virsh console caelus             # serial console; exit with Ctrl+]
sudo virsh domifaddr caelus --source agent   # guest IPs via qemu-guest-agent
```

VM facts:
- 16 GiB RAM, 4 vCPU, `--cpu host-passthrough`, `--machine pc` (i440fx / seabios).
- Disk: `/var/lib/libvirt/images/caelus.qcow2` on a virtio-scsi bus.
- `autostart` is enabled, so the VM comes back on a `nuc` reboot.
- qemu-guest-agent is installed in the guest and wired to a virtio channel.

## Accessing the cluster

The kubeconfig lives in the guest at `/etc/rancher/k3s/k3s.yaml`. To use it from
another machine, copy it out and rewrite the server address to the VM's IP:

```bash
ssh ubuntu@192.168.0.159 sudo cat /etc/rancher/k3s/k3s.yaml \
  | sed 's/127.0.0.1/192.168.0.159/g' > k8s/kubeconfigs/caelus.yaml
chmod 600 k8s/kubeconfigs/caelus.yaml
kubectl --kubeconfig k8s/kubeconfigs/caelus.yaml get nodes
```

## Backups & restore

The whole cluster is one flat qcow2 file, so backups are simple:

```bash
sudo virsh shutdown caelus
sudo cp /var/lib/libvirt/images/caelus.qcow2 /path/to/backup/caelus-$(date +%F).qcow2
sudo virsh start caelus
# (or use `virsh snapshot-create-as caelus <name>` for a live snapshot)
```

## Recreating the VM from a qcow2

If you ever need to re-import the disk (new host, or from a backup), define the
domain with `virt-install`, keeping the MAC so the IP is preserved:

```bash
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst qemu-utils

sudo virt-install \
  --name caelus \
  --memory 16384 \
  --vcpus 4 \
  --cpu host-passthrough \
  --machine pc \
  --import \
  --disk path=/var/lib/libvirt/images/caelus.qcow2,bus=scsi,format=qcow2 \
  --controller scsi,model=virtio-scsi \
  --network bridge=br0,model=virtio,mac=BC:24:11:E7:0D:1B \
  --os-variant ubuntu24.04 \
  --channel unix,target_type=virtio,name=org.qemu.guest_agent.0 \
  --graphics none \
  --console pty,target_type=serial \
  --noautoconsole \
  --autostart
```

---

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
