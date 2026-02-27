# NOTE: Ingress is managed manually since the terraform kubernetes provider
# doesn't fully support networking.k8s.io/v1 ingresses.
# Run: kubectl apply -f - <<EOF
# apiVersion: networking.k8s.io/v1
# kind: Ingress
# metadata:
#   name: caelus-ingress
#   namespace: caelus
#   annotations:
#     traefik.ingress.kubernetes.io/rewrite-target: /
# spec:
#   ingressClassName: traefik
#   rules:
#   - host: app.deprutser.be
#     http:
#       paths:
#       - path: /api
#         pathType: Prefix
#         backend:
#           service:
#             name: caelus-api
#             port:
#               number: 8000
#       - path: /
#         pathType: Prefix
#         backend:
#           service:
#             name: caelus-ui
#             port:
#               number: 80
# EOF
