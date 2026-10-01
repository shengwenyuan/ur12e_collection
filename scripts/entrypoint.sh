#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
case "${1:-}" in
  bash|/bin/bash|sh|/bin/sh|ur12e|ur-collect) exec "$@" ;;
esac
exec ur-collect "$@"
