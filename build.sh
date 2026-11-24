#!/usr/bin/env bash
# Render build script: install, collect static files, migrate, ensure the first Admin exists.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createadmin --from-env
