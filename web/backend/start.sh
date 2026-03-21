#!/usr/bin/env bash
cd "$(dirname "$0")"
pip install -r requirements.txt -q
uvicorn main:app --host 0.0.0.0 --port 8010 --reload
