@echo off
REM Collecte automatique ImmoInsight TN (scrapers, retraits, ETL, re-entrainement, rapport).
REM Journal : logs\scheduler.log ; historique des executions : collection Mongo scheduler_logs.
REM Demarrage automatique a l'ouverture de session (une fois, dans une invite de commande) :
REM   schtasks /Create /SC ONLOGON /TN "ImmoInsight Scheduler" /TR "\"%~f0\""
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
py -3.13 -m scrapers.main --scheduler >> logs\scheduler.log 2>&1
