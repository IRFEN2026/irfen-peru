@echo off
python -m pip install -r requirements.txt
python scripts\fetch_imerg.py --demo
python -m http.server 8000 --directory site
