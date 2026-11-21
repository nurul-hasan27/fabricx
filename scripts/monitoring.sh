#!/bin/bash
# Start/stop Prometheus + Grafana for the lab.  Usage: scripts/monitoring.sh up|down
# Runs where Docker runs (the OrbStack VM from the Mac, or the CI runner with RUN=sudo).
# The exporter (`fabricx exporter`) runs next to the code: on the Mac (reached from the VM as host.orb.internal)
# or on the CI runner itself.
set -euo pipefail
RUN=${RUN:-orb -m fabricx-lab sudo}
DIR=$(cd "$(dirname "$0")/.." && pwd)/monitoring
PROM=prom/prometheus:v3.1.0
GRAF=grafana/grafana:11.4.0
case "${1:-}" in
  up)
    if [ -z "${EXPORTER_ADDR:-}" ]; then
      if command -v orb >/dev/null; then EXPORTER_ADDR=$($RUN sh -c "getent ahostsv4 host.orb.internal | head -1 | cut -d' ' -f1")
      else EXPORTER_ADDR=127.0.0.1; fi
    fi
    $RUN docker rm -f fabricx-prometheus fabricx-grafana >/dev/null 2>&1 || true
    $RUN docker run -d --name fabricx-prometheus --network host --add-host "exporter:$EXPORTER_ADDR" \
      -v "$DIR/prometheus.yml:/etc/prometheus/prometheus.yml:ro" $PROM >/dev/null
    $RUN docker run -d --name fabricx-grafana --network host \
      -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin -e GF_AUTH_DISABLE_LOGIN_FORM=true \
      -e GF_ANALYTICS_REPORTING_ENABLED=false -e GF_ANALYTICS_CHECK_FOR_UPDATES=false \
      -e GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/fabricx.json \
      -v "$DIR/grafana/provisioning:/etc/grafana/provisioning:ro" \
      -v "$DIR/grafana/dashboards:/var/lib/grafana/dashboards:ro" $GRAF >/dev/null
    echo "prometheus :9090, grafana :3000 (exporter expected at $EXPORTER_ADDR:9101)" ;;
  down)
    $RUN docker rm -f fabricx-prometheus fabricx-grafana >/dev/null 2>&1 || true; echo "monitoring stopped" ;;
  *) echo "usage: $0 up|down"; exit 2 ;;
esac
