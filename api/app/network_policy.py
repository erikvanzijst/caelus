from __future__ import annotations

from typing import Any

from app.config import CaelusSettings

# Namespace labels that make the NetworkPolicy jail non-bypassable and mark the
# namespace as a Caelus tenant. Pod Security Admission ``baseline`` forbids the
# hostNetwork / hostPort / hostPath / privileged escapes that would otherwise let
# a pod sidestep pod-network filtering entirely (a hostNetwork pod uses the node's
# network namespace, which NetworkPolicy never sees). ``caelus.dev/tenant`` lets
# shared services and cluster-wide policy select tenant namespaces.
TENANT_NAMESPACE_LABELS: dict[str, str] = {
    "caelus.dev/tenant": "true",
    "pod-security.kubernetes.io/enforce": "baseline",
    "pod-security.kubernetes.io/enforce-version": "latest",
}


def build_tenant_baseline_policy(*, namespace: str, settings: CaelusSettings) -> dict[str, Any]:
    """Render the platform-owned baseline NetworkPolicy for a tenant namespace.

    Default-deny in both directions (``podSelector: {}`` + both policy types),
    then allow exactly:

    - ingress from the shared Traefik edge (any port, so per-chart service ports
      never need standardizing) plus free traffic within the namespace;
    - egress: free traffic within the namespace, DNS, the shared SMTP relay, and
      the public internet minus every internal range (LAN, node, other tenants,
      the service CIDR, and link-local/cloud-metadata).

    The policy is byte-for-byte identical for every tenant; only
    ``metadata.namespace`` varies. That is what lets a single definition, applied
    per namespace, cover the whole fleet -- and why a fleet-wide update is just a
    re-apply of this render (see ``caelus sync-network-policies``).
    """
    dns_ports = [
        {"port": 53, "protocol": "UDP"},
        {"port": 53, "protocol": "TCP"},
    ]
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": settings.tenant_netpol_name,
            "namespace": namespace,
            "labels": {"app.kubernetes.io/managed-by": "caelus"},
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [
                {  # shared Traefik edge -> any pod, any port
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": settings.ingress_namespace
                                }
                            },
                            "podSelector": {
                                "matchLabels": {"app.kubernetes.io/name": settings.ingress_pod_label}
                            },
                        }
                    ]
                },
                {"from": [{"podSelector": {}}]},  # free traffic within the namespace
            ],
            "egress": [
                {"to": [{"podSelector": {}}]},  # free traffic within the namespace
                {  # DNS to kube-dns pods (post-DNAT match)
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                            },
                            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                        }
                    ],
                    "ports": dns_ports,
                },
                {  # DNS ClusterIP (pre-DNAT belt & suspenders)
                    "to": [{"ipBlock": {"cidr": f"{settings.dns_cluster_ip}/32"}}],
                    "ports": dns_ports,
                },
                {  # shared SMTP relay
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": settings.mailer_namespace}
                            },
                            "podSelector": {"matchLabels": {"app": settings.mailer_pod_label}},
                        }
                    ],
                    "ports": [{"port": settings.mailer_port, "protocol": "TCP"}],
                },
                {  # internet, minus every internal range + link-local/metadata
                    "to": [
                        {
                            "ipBlock": {
                                "cidr": "0.0.0.0/0",
                                "except": list(settings.tenant_egress_except_cidrs),
                            }
                        }
                    ]
                },
            ],
        },
    }
