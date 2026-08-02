#!/bin/sh
set -eu
node --check app.js
node --check demo-data.js
node --check config.js
python tests/static_check.py
