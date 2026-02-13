#!/usr/bin/env bash
set -euo pipefail

# Provisions a development VM in Proxmox by cloning a cloud-image template,
# waits for SSH, installs k3s, and writes a local kubeconfig.
# Secrets are read from environment variables; nothing sensitive is hardcoded.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="${SCRIPT_DIR}/.env"

load_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    # Source a trusted local env file and export defined variables.
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

load_env_file "${K8S_ENV_FILE:-$DEFAULT_ENV_FILE}"

PROXMOX_HOST="${PROXMOX_HOST:-192.168.0.15}"
PROXMOX_API_PORT="${PROXMOX_API_PORT:-8006}"
PROXMOX_API_BASE="https://${PROXMOX_HOST}:${PROXMOX_API_PORT}/api2/json"
PROXMOX_NODE="${PROXMOX_NODE:-}"
PROXMOX_API_TOKEN="${PROXMOX_API_TOKEN:-}"
PROXMOX_USER="${PROXMOX_USER:-}"
PROXMOX_PASSWORD="${PROXMOX_PASSWORD:-}"

TEMPLATE_VM_ID="${TEMPLATE_VM_ID:-9000}"
TEMPLATE_VM_NAME="${TEMPLATE_VM_NAME:-}"

VM_NAME="${VM_NAME:-dev-k3s-$(date +%Y%m%d-%H%M%S)}"
VM_ID="${VM_ID:-}"
VM_MEMORY_MB="${VM_MEMORY_MB:-8192}"
VM_DISK_GB="${VM_DISK_GB:-30}"
VM_CORES="${VM_CORES:-4}"
VM_BRIDGE="${VM_BRIDGE:-vmbr0}"
DNS_SERVER="${DNS_SERVER:-192.168.0.9}"

CLOUDINIT_STORAGE="${CLOUDINIT_STORAGE:-local-lvm}"
FULL_CLONE="${FULL_CLONE:-1}"
DRY_RUN="${DRY_RUN:-0}"

SSH_USER="${SSH_USER:-ubuntu}"
SSH_PUBLIC_KEY_PATH="${SSH_PUBLIC_KEY_PATH:-$HOME/.ssh/id_ed25519.pub}"
SSH_PRIVATE_KEY_PATH="${SSH_PRIVATE_KEY_PATH:-$HOME/.ssh/id_ed25519}"
SSH_PORT="${SSH_PORT:-22}"

SSH_WAIT_TIMEOUT_SEC="${SSH_WAIT_TIMEOUT_SEC:-1800}"
KUBECONFIG_DIR="${KUBECONFIG_DIR:-$(pwd)/k8s/kubeconfigs}"

AUTH_COOKIE=""
CSRF_TOKEN=""

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--dry-run|-n]

Options:
  -n, --dry-run   Validate configuration and API access only; do not create or start a VM.
  -h, --help      Show this help.
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n|--dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_env_or_token_auth() {
  if [[ -n "$PROXMOX_API_TOKEN" ]]; then
    return
  fi
  if [[ -z "$PROXMOX_USER" || -z "$PROXMOX_PASSWORD" ]]; then
    echo "Set either PROXMOX_API_TOKEN or both PROXMOX_USER and PROXMOX_PASSWORD." >&2
    exit 1
  fi
}

build_auth_args() {
  local -n _out=$1
  _out=(-k -sS)
  if [[ -n "$PROXMOX_API_TOKEN" ]]; then
    _out+=( -H "Authorization: PVEAPIToken=${PROXMOX_API_TOKEN}" )
  else
    _out+=( -H "CSRFPreventionToken: ${CSRF_TOKEN}" --cookie "PVEAuthCookie=${AUTH_COOKIE}" )
  fi
}

api_login_if_needed() {
  if [[ -n "$PROXMOX_API_TOKEN" ]]; then
    return
  fi

  local resp
  resp=$(curl -k -sS \
    --data-urlencode "username=${PROXMOX_USER}" \
    --data-urlencode "password=${PROXMOX_PASSWORD}" \
    "${PROXMOX_API_BASE}/access/ticket")

  AUTH_COOKIE=$(echo "$resp" | jq -r '.data.ticket')
  CSRF_TOKEN=$(echo "$resp" | jq -r '.data.CSRFPreventionToken')

  if [[ -z "$AUTH_COOKIE" || "$AUTH_COOKIE" == "null" || -z "$CSRF_TOKEN" || "$CSRF_TOKEN" == "null" ]]; then
    echo "Failed to authenticate to Proxmox API." >&2
    echo "$resp" >&2
    exit 1
  fi
}

api_get() {
  local path="$1"
  local auth_args=()
  build_auth_args auth_args
  curl "${auth_args[@]}" "${PROXMOX_API_BASE}${path}"
}

api_post_form() {
  local path="$1"
  shift
  local auth_args=()
  build_auth_args auth_args

  local data_args=()
  local kv
  for kv in "$@"; do
    data_args+=( --data-urlencode "$kv" )
  done

  curl "${auth_args[@]}" -X POST "${data_args[@]}" "${PROXMOX_API_BASE}${path}"
}

api_put_form() {
  local path="$1"
  shift
  local auth_args=()
  build_auth_args auth_args

  local data_args=()
  local kv
  for kv in "$@"; do
    data_args+=( --data-urlencode "$kv" )
  done

  curl "${auth_args[@]}" -X PUT "${data_args[@]}" "${PROXMOX_API_BASE}${path}"
}

assert_api_ok() {
  local resp="$1"
  local context="$2"
  local message errors
  message=$(echo "$resp" | jq -r '.message // empty')
  errors=$(echo "$resp" | jq -r '.errors // empty')

  if [[ -n "$message" || -n "$errors" ]]; then
    echo "${context} failed." >&2
    echo "$resp" >&2
    exit 1
  fi
}

wait_for_task() {
  local node="$1"
  local upid="$2"
  local timeout="${3:-600}"
  local started_at
  started_at=$(date +%s)

  while true; do
    local resp status exitstatus now
    resp=$(api_get "/nodes/${node}/tasks/${upid}/status")
    status=$(echo "$resp" | jq -r '.data.status')
    exitstatus=$(echo "$resp" | jq -r '.data.exitstatus // ""')

    if [[ "$status" == "stopped" ]]; then
      if [[ "$exitstatus" != "OK" ]]; then
        echo "Proxmox task failed: ${upid} exitstatus=${exitstatus}" >&2
        echo "$resp" >&2
        return 1
      fi
      return 0
    fi

    now=$(date +%s)
    if (( now - started_at > timeout )); then
      echo "Timed out waiting for Proxmox task: ${upid}" >&2
      return 1
    fi

    sleep 2
  done
}

resolve_node() {
  if [[ -n "$PROXMOX_NODE" ]]; then
    echo "$PROXMOX_NODE"
    return
  fi

  local resp count
  resp=$(api_get "/nodes")
  count=$(echo "$resp" | jq '.data | length')

  if [[ "$count" -eq 1 ]]; then
    echo "$resp" | jq -r '.data[0].node'
    return
  fi

  echo "Multiple Proxmox nodes detected. Set PROXMOX_NODE explicitly." >&2
  echo "$resp" | jq -r '.data[].node' >&2
  exit 1
}

resolve_vmid() {
  if [[ -n "$VM_ID" ]]; then
    echo "$VM_ID"
    return
  fi

  api_get "/cluster/nextid" | jq -r '.data'
}

resolve_template_vmid() {
  if [[ -n "$TEMPLATE_VM_ID" ]]; then
    echo "$TEMPLATE_VM_ID"
    return
  fi

  if [[ -z "$TEMPLATE_VM_NAME" ]]; then
    echo "Set TEMPLATE_VM_ID or TEMPLATE_VM_NAME for the cloud-image template." >&2
    exit 1
  fi

  local resp template_id
  resp=$(api_get "/cluster/resources?type=vm")
  template_id=$(echo "$resp" | jq -r --arg name "$TEMPLATE_VM_NAME" '.data[] | select(.template == 1 and .name == $name) | .vmid' | head -n1)

  if [[ -z "$template_id" || "$template_id" == "null" ]]; then
    echo "Could not find template named '${TEMPLATE_VM_NAME}'." >&2
    exit 1
  fi

  echo "$template_id"
}

assert_template() {
  local node="$1"
  local vmid="$2"
  local resp is_template
  resp=$(api_get "/nodes/${node}/qemu/${vmid}/config")
  is_template=$(echo "$resp" | jq -r '.data.template // 0')
  if [[ "$is_template" != "1" ]]; then
    echo "VM ${vmid} on node ${node} is not marked as a template." >&2
    exit 1
  fi
}

ensure_cloudinit_drive() {
  local node="$1"
  local vmid="$2"
  local storage="$3"
  local resp current_ide2

  resp=$(api_get "/nodes/${node}/qemu/${vmid}/config")
  current_ide2=$(echo "$resp" | jq -r '.data.ide2 // ""')

  if [[ "$current_ide2" == *":cloudinit"* || "$current_ide2" == *"cloudinit"* ]]; then
    echo "Cloud-init drive already present (${current_ide2}), skipping create."
    return 0
  fi

  if [[ -n "$current_ide2" ]]; then
    echo "VM ${vmid} already has ide2 configured (${current_ide2}), refusing to overwrite." >&2
    return 1
  fi

  local cloudinit_resp cloudinit_upid
  cloudinit_resp=$(api_post_form "/nodes/${node}/qemu/${vmid}/config" "ide2=${storage}:cloudinit")
  cloudinit_upid=$(echo "$cloudinit_resp" | jq -r '.data // ""')
  if [[ -n "$cloudinit_upid" ]]; then
    wait_for_task "$node" "$cloudinit_upid" 120
  fi
}

can_ssh() {
  local ip="$1"
  ssh -o BatchMode=yes \
      -o ConnectTimeout=5 \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o IdentitiesOnly=yes \
      -i "$SSH_PRIVATE_KEY_PATH" \
      -p "$SSH_PORT" \
      "${SSH_USER}@${ip}" \
      "echo ok" >/dev/null 2>&1
}

get_ip_from_qemu_agent() {
  local node="$1"
  local vmid="$2"
  local resp ip

  resp=$(api_get "/nodes/${node}/qemu/${vmid}/agent/network-get-interfaces" || true)
  ip=$(echo "$resp" | jq -r '
    .data.result[]?.["ip-addresses"][]?
    | select(."ip-address-type" == "ipv4")
    | ."ip-address"
    | select(startswith("127.") | not)
    | select(startswith("169.254.") | not)
  ' | head -n1)

  if [[ -n "$ip" && "$ip" != "null" ]]; then
    echo "$ip"
  fi
}

wait_for_ssh_ip() {
  local node="$1"
  local vmid="$2"
  local timeout="$3"
  local started_at
  started_at=$(date +%s)

  while true; do
    local now
    now=$(date +%s)
    if (( now - started_at > timeout )); then
      echo "Timed out waiting for VM to become reachable over SSH." >&2
      return 1
    fi

    local agent_ip
    agent_ip=$(get_ip_from_qemu_agent "$node" "$vmid" || true)
    if [[ -n "$agent_ip" ]] && can_ssh "$agent_ip"; then
      echo "$agent_ip"
      return 0
    fi

    sleep 5
  done
}

install_k3s() {
  local ip="$1"
  ssh -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o IdentitiesOnly=yes \
      -i "$SSH_PRIVATE_KEY_PATH" \
      -p "$SSH_PORT" \
      "${SSH_USER}@${ip}" \
      "set -euo pipefail; curl -sfL https://get.k3s.io | sh -"

  ssh -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o IdentitiesOnly=yes \
      -i "$SSH_PRIVATE_KEY_PATH" \
      -p "$SSH_PORT" \
      "${SSH_USER}@${ip}" \
      "sudo systemctl is-active --quiet k3s"
}

write_local_kubeconfig() {
  local ip="$1"
  local vmid="$2"
  local name="$3"

  mkdir -p "$KUBECONFIG_DIR"
  local out_file="${KUBECONFIG_DIR}/${name}-${vmid}.yaml"

  ssh -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o IdentitiesOnly=yes \
      -i "$SSH_PRIVATE_KEY_PATH" \
      -p "$SSH_PORT" \
      "${SSH_USER}@${ip}" \
      "sudo cat /etc/rancher/k3s/k3s.yaml" \
      | sed "s/127.0.0.1/${ip}/g" > "$out_file"

  chmod 600 "$out_file"
  echo "$out_file"
}

main() {
  parse_args "$@"

  require_cmd curl
  require_cmd jq
  require_cmd ssh
  if [[ "$DRY_RUN" != "1" ]]; then
    require_cmd kubectl
  fi

  if [[ ! -f "$SSH_PUBLIC_KEY_PATH" ]]; then
    echo "SSH public key not found: ${SSH_PUBLIC_KEY_PATH}" >&2
    exit 1
  fi
  if [[ ! -f "$SSH_PRIVATE_KEY_PATH" ]]; then
    echo "SSH private key not found: ${SSH_PRIVATE_KEY_PATH}" >&2
    exit 1
  fi

  require_env_or_token_auth
  api_login_if_needed

  local node template_vmid vmid ssh_pub_key
  node=$(resolve_node)
  template_vmid=$(resolve_template_vmid)
  assert_template "$node" "$template_vmid"
  vmid=$(resolve_vmid)
  ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

  if [[ "$DRY_RUN" == "1" ]]; then
    cat <<DONE
Dry-run successful.
Resolved Proxmox node: ${node}
Resolved template VMID: ${template_vmid}
Next VMID: ${vmid}
VM name to create: ${VM_NAME}
No VM was created or modified.
DONE
    return 0
  fi

  echo "[1/8] Cloning template ${template_vmid} -> VM ${VM_NAME} (vmid=${vmid}) on node ${node}..."
  local clone_resp clone_upid
  clone_resp=$(api_post_form "/nodes/${node}/qemu/${template_vmid}/clone" \
    "newid=${vmid}" \
    "name=${VM_NAME}" \
    "full=${FULL_CLONE}")
  clone_upid=$(echo "$clone_resp" | jq -r '.data')
  if [[ -z "$clone_upid" || "$clone_upid" == "null" ]]; then
    echo "Failed to clone template." >&2
    echo "$clone_resp" >&2
    exit 1
  fi
  wait_for_task "$node" "$clone_upid" 900

  echo "[2/8] Configuring VM compute/network/cloud-init settings..."
  local cfg_resp cfg_upid
  cfg_resp=$(api_post_form "/nodes/${node}/qemu/${vmid}/config" \
    "memory=${VM_MEMORY_MB}" \
    "balloon=0" \
    "cores=${VM_CORES}" \
    "net0=virtio,bridge=${VM_BRIDGE}" \
    "ipconfig0=ip=dhcp" \
    "nameserver=${DNS_SERVER}" \
    "ciuser=${SSH_USER}" \
    "sshkeys=${ssh_pub_key}" \
    "agent=1")
  assert_api_ok "$cfg_resp" "VM config update"
  cfg_upid=$(echo "$cfg_resp" | jq -r '.data // ""')
  if [[ -n "$cfg_upid" ]]; then
    wait_for_task "$node" "$cfg_upid" 120
  fi

  local applied_cfg applied_memory
  applied_cfg=$(api_get "/nodes/${node}/qemu/${vmid}/config")
  assert_api_ok "$applied_cfg" "VM config readback"
  applied_memory=$(echo "$applied_cfg" | jq -r '.data.memory // ""')
  if [[ "$applied_memory" != "$VM_MEMORY_MB" ]]; then
    echo "Memory setting did not apply. Expected ${VM_MEMORY_MB} MB, got ${applied_memory:-<empty>} MB." >&2
    echo "$applied_cfg" >&2
    exit 1
  fi

  echo "[3/8] Ensuring cloud-init drive exists on ${CLOUDINIT_STORAGE}..."
  ensure_cloudinit_drive "$node" "$vmid" "$CLOUDINIT_STORAGE"

  echo "[4/8] Resizing disk scsi0 to ${VM_DISK_GB}G..."
  local resize_resp resize_upid
  resize_resp=$(api_put_form "/nodes/${node}/qemu/${vmid}/resize" \
    "disk=scsi0" \
    "size=${VM_DISK_GB}G")
  resize_upid=$(echo "$resize_resp" | jq -r '.data')
  if [[ -z "$resize_upid" || "$resize_upid" == "null" ]]; then
    echo "Failed to resize disk." >&2
    echo "$resize_resp" >&2
    exit 1
  fi
  wait_for_task "$node" "$resize_upid" 300

  echo "[5/8] Starting VM ${vmid}..."
  local start_resp start_upid
  start_resp=$(api_post_form "/nodes/${node}/qemu/${vmid}/status/start")
  start_upid=$(echo "$start_resp" | jq -r '.data')
  if [[ -z "$start_upid" || "$start_upid" == "null" ]]; then
    echo "Failed to start VM." >&2
    echo "$start_resp" >&2
    exit 1
  fi
  wait_for_task "$node" "$start_upid" 120

  echo "[6/8] Waiting for VM SSH to come online (timeout=${SSH_WAIT_TIMEOUT_SEC}s)..."
  local vm_ip
  vm_ip=$(wait_for_ssh_ip "$node" "$vmid" "$SSH_WAIT_TIMEOUT_SEC")
  echo "VM reachable via SSH at: ${vm_ip}"

  echo "[7/8] Installing k3s and writing local kubeconfig..."
  install_k3s "$vm_ip"
  local kubeconfig_file
  kubeconfig_file=$(write_local_kubeconfig "$vm_ip" "$vmid" "$VM_NAME")

  echo "$vm_ip" > "$(pwd)/last_vm_ip.txt"

  echo "[8/8] Verifying cluster with kubectl..."
  kubectl --kubeconfig "$kubeconfig_file" get nodes

  cat <<DONE
Provisioning complete.
VM name: ${VM_NAME}
VM ID: ${vmid}
VM IP: ${vm_ip}
Kubeconfig: ${kubeconfig_file}
DONE
}

main "$@"
