#!/bin/bash
cd "/Users/leblancbahiga/Downloads/Assistant IA" || exit 1
exec .venv/bin/python3 nuru_dashboard.py "$@"
