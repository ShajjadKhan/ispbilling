#!/bin/bash
cd /home/tserver/ispbilling
source ./venv/bin/activate
exec uvicorn main:app --host 0.0.0.0 --port 8088 >> uvicorn.log 2>&1
