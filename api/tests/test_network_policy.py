from __future__ import annotations

from app.config import CaelusSettings
from app.network_policy import TENANT_NAMESPACE_LABELS, build_tenant_baseline_policy


def _policy(namespace: str = "tenant-abc"):
    return build_tenant_baseline_policy(namespace=namespace, settings=CaelusSettings(_env_file=None))


def test_policy_is_namespaced_and_default_deny_both_directions() -> None:
    policy = _policy("tenant-abc")
    assert policy["apiVersion"] == "networking.k8s.io/v1"
    assert policy["kind"] == "NetworkPolicy"
    assert policy["metadata"]["namespace"] == "tenant-abc"
    assert policy["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "caelus"
    spec = policy["spec"]
    # Empty podSelector + both policy types => default-deny, then allow-list below.
    assert spec["podSelector"] == {}
    assert set(spec["policyTypes"]) == {"Ingress", "Egress"}


def test_only_traefik_sshpiper_and_own_namespace_may_ingress() -> None:
    ingress = _policy()["spec"]["ingress"]
    traefik = ingress[0]["from"][0]
    assert traefik["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] == "kube-system"
    assert traefik["podSelector"]["matchLabels"]["app.kubernetes.io/name"] == "traefik"
    # No port restriction on the trusted edge, so per-chart service ports don't matter.
    assert "ports" not in ingress[0]
    sshpiper = ingress[1]["from"][0]
    assert sshpiper["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] == "sshpiper"
    assert sshpiper["podSelector"]["matchLabels"]["app"] == "sshpiper"
    # Free traffic within the namespace (multi-pod apps).
    assert ingress[2]["from"] == [{"podSelector": {}}]
    assert len(ingress) == 3


def test_sftp_router_ingress_is_port_scoped() -> None:
    # Unlike the Traefik rule, the SFTP router may only reach the sidecar port:
    # it has no business on app ports, and the scoping keeps a compromised (or
    # cross-environment) router from becoming a bridge into tenant workloads.
    sshpiper_rule = _policy()["spec"]["ingress"][1]
    assert sshpiper_rule["ports"] == [{"port": 2222, "protocol": "TCP"}]


def test_sftp_router_selector_is_environment_scoped() -> None:
    # Each environment's reconciler renders its own router namespace, so the
    # dev router never matches prod tenant policies and vice versa. This is the
    # sole enforcement layer: sshpiper's kubernetes plugin cannot filter its
    # cluster-wide Pipe watch by namespace (spike finding).
    settings = CaelusSettings(
        _env_file=None, sshpiper_namespace="sshpiper-dev", sftp_sidecar_port=2323
    )
    policy = build_tenant_baseline_policy(namespace="tenant-abc", settings=settings)
    rule = policy["spec"]["ingress"][1]
    selector = rule["from"][0]["namespaceSelector"]["matchLabels"]
    assert selector["kubernetes.io/metadata.name"] == "sshpiper-dev"
    assert rule["ports"] == [{"port": 2323, "protocol": "TCP"}]


def test_egress_allows_intra_namespace_dns_and_mailer_only_internally() -> None:
    egress = _policy()["spec"]["egress"]
    assert egress[0]["to"] == [{"podSelector": {}}]  # intra-namespace

    dns_rules = [rule for rule in egress if rule.get("ports") == [
        {"port": 53, "protocol": "UDP"},
        {"port": 53, "protocol": "TCP"},
    ]]
    # Both kube-dns pod selector (post-DNAT) and the ClusterIP (pre-DNAT) are allowed.
    assert any("namespaceSelector" in rule["to"][0] for rule in dns_rules)
    assert any(rule["to"][0].get("ipBlock", {}).get("cidr") == "10.43.0.10/32" for rule in dns_rules)

    mailer = next(r for r in egress if r.get("ports") == [{"port": 25, "protocol": "TCP"}])
    assert mailer["to"][0]["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] == "mailer"
    assert mailer["to"][0]["podSelector"]["matchLabels"]["app"] == "smtp"


def test_internet_egress_excludes_all_private_ranges_and_metadata() -> None:
    egress = _policy()["spec"]["egress"]
    internet = next(r for r in egress if r["to"][0].get("ipBlock", {}).get("cidr") == "0.0.0.0/0")
    excluded = set(internet["to"][0]["ipBlock"]["except"])
    # LAN, node, other tenants/services (10/8 covers the k3s pod+service CIDRs), and
    # link-local/cloud-metadata (169.254/16 — credential-theft vector) are all denied.
    assert {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"} <= excluded
    assert "ports" not in internet  # all ports to the public internet


def test_tenant_labels_enforce_pod_security_baseline() -> None:
    # Pod Security Admission `baseline` is what stops a tenant from bypassing the
    # NetworkPolicy via hostNetwork; without it the netpol is theater.
    assert TENANT_NAMESPACE_LABELS["pod-security.kubernetes.io/enforce"] == "baseline"
    assert TENANT_NAMESPACE_LABELS["caelus.dev/tenant"] == "true"
