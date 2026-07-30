resource "helm_release" "loki" {
  name      = "loki"
  namespace = var.namespace
  # Bump the version in the URL on upgrade (latest:
  # https://github.com/grafana/loki/blob/main/production/helm/loki/Chart.yaml).
  chart = "https://github.com/grafana/helm-charts/releases/download/helm-loki-6.41.1/loki-6.41.1.tgz"

  # https://github.com/grafana/loki/blob/main/production/helm/loki/values.yaml
  values = [
    yamlencode({
      # https://grafana.com/docs/loki/latest/setup/install/helm/install-monolithic/
      deploymentMode = "SingleBinary"
      singleBinary = {
        replicas = 1
        persistence = {
          enabled = true
          size    = "10Gi"
        }
      }
      loki = {
        auth_enabled = false
        commonConfig = {
          replication_factor = 1
        }
        schemaConfig = {
          configs = [{
            from         = "2025-10-01"
            object_store = "filesystem"
            store        = "tsdb"
            schema       = "v13"
            index = {
              prefix = "index_"
              period = "24h"
            }
          }]
        }
        pattern_ingester = {
          enabled = true
        }
        storage = {
          type = "filesystem"
        }
        ui = {
          enabled = true
        }
      }
      # Shrink the memcached caches from their multi-node chart defaults
      # (chunks 8192MB, results 1024MB) to homelab scale. The defaults
      # hold nearly the entire ~10Gi log store in RAM; the chart sets the
      # pod's memory request/limit to allocatedMemory * ~1.2. Reclaims ~7.7Gi RAM.
      chunksCache = {
        allocatedMemory = 512
      }
      resultsCache = {
        allocatedMemory = 128
      }

      # Zero out replica counts of other deployment modes:
      backend = {
        replicas = 0
      }
      read = {
        replicas = 0
      }
      write = {
        replicas = 0
      }
      ingester = {
        replicas = 0
      }
      querier = {
        replicas = 0
      }
      queryFrontend = {
        replicas = 0
      }
      queryScheduler = {
        replicas = 0
      }
      distributor = {
        replicas = 0
      }
      compactor = {
        replicas = 0
      }
      indexGateway = {
        replicas = 0
      }
      bloomCompactor = {
        replicas = 0
      }
      bloomGateway = {
        replicas = 0
      }
    })
  ]
}

resource "helm_release" "promtail" {
  name       = "promtail"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "promtail"
  version    = "6.17.0" # check latest version at https://github.com/grafana/helm-charts/blob/main/charts/promtail/Chart.yaml
  namespace  = var.namespace

  values = [
    yamlencode({
      config = {
        server = {
          http_listen_port = 9080
          grpc_listen_port = 0
        }
        clients = [
          {
            url = "http://loki.${var.namespace}.svc.cluster.local:3100/loki/api/v1/push"
          }
        ]

        # Helpful example: https://github.com/grafana/loki/issues/4381
        snippets = {
          scrapeConfigs = <<-EOT
            - job_name: kubernetes-pods
              pipeline_stages:
                - cri: {}
                # Parse Traefik CLF access logs (kube-system/traefik) so the
                # upstream app is queryable. Non-access lines (Traefik's own
                # app logs) simply don't match the regex and pass through untouched.
                - match:
                    selector: '{namespace="kube-system", container="traefik"}'
                    stages:
                      - regex:
                          expression: '^(?P<remote_addr>\S+) - (?P<remote_user>\S+) \[(?P<time_local>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) (?P<protocol>[^"]+)" (?P<status>\d{3}) (?P<bytes>\d+) "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)" (?P<request_count>\d+) "(?P<router>[^"]*)" "(?P<upstream>[^"]*)" (?P<duration>\S+)$'
                      # Low-cardinality fields -> stream labels (queryable/cheap)
                      - labels:
                          method:
                          status:
                          router:
                      # High-cardinality fields -> structured metadata (queryable
                      # without exploding stream cardinality; needs v13 schema)
                      - structured_metadata:
                          remote_addr:
                          path:
                          user_agent:
                          upstream:
                          duration:
              kubernetes_sd_configs:
                - role: pod
              relabel_configs:
                - source_labels:
                    - __meta_kubernetes_pod_controller_name
                  regex: ([0-9a-z-.]+?)(-[0-9a-f]{8,10})?
                  action: replace
                  target_label: __tmp_controller_name
                - source_labels:
                    - __meta_kubernetes_pod_label_app_kubernetes_io_name
                    - __meta_kubernetes_pod_label_app
                    - __tmp_controller_name
                    - __meta_kubernetes_pod_name
                  regex: ^;*([^;]+)(;.*)?$
                  action: replace
                  target_label: app
                - source_labels:
                    - __meta_kubernetes_pod_label_app_kubernetes_io_instance
                    - __meta_kubernetes_pod_label_instance
                  regex: ^;*([^;]+)(;.*)?$
                  action: replace
                  target_label: instance
                - source_labels:
                    - __meta_kubernetes_pod_label_app_kubernetes_io_component
                    - __meta_kubernetes_pod_label_component
                  regex: ^;*([^;]+)(;.*)?$
                  action: replace
                  target_label: component
                - action: replace
                  source_labels:
                  - __meta_kubernetes_pod_node_name
                  target_label: node_name
                - action: replace
                  source_labels:
                  - __meta_kubernetes_namespace
                  target_label: namespace
                - action: replace
                  replacement: $1
                  separator: /
                  source_labels:
                  - namespace
                  - app
                  target_label: job
                - action: replace
                  source_labels:
                  - __meta_kubernetes_pod_name
                  target_label: pod
                - action: replace
                  source_labels:
                  - __meta_kubernetes_pod_container_name
                  target_label: container
                - action: replace
                  replacement: /var/log/pods/*$1/*.log
                  separator: /
                  source_labels:
                  - __meta_kubernetes_pod_uid
                  - __meta_kubernetes_pod_container_name
                  target_label: __path__
                - action: replace
                  regex: true/(.*)
                  replacement: /var/log/pods/*$1/*.log
                  separator: /
                  source_labels:
                  - __meta_kubernetes_pod_annotationpresent_kubernetes_io_config_hash
                  - __meta_kubernetes_pod_annotation_kubernetes_io_config_hash
                  - __meta_kubernetes_pod_container_name
                  target_label: __path__
          EOT
        }
      }
    })
  ]
}
