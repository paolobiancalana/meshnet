@echo off
REM Script per avviare il server di discovery su Windows

REM Impostazioni predefinite
set PORT=8000
set BIND=0.0.0.0

REM Parsing parametri
:loop
if "%1"=="" goto :continue
if "%1"=="--port" (
    set PORT=%2
    shift
    shift
    goto :loop
)
if "%1"=="--bind" (
    set BIND=%2
    shift
    shift
    goto :loop
)
if "%1"=="--help" (
    echo Utilizzo: %0 [opzioni]
    echo Opzioni:
    echo   --port PORTA     Porta su cui ascoltare (default: 8000)
    echo   --bind INDIRIZZO Indirizzo su cui ascoltare (default: 0.0.0.0)
    echo   --help           Mostra questa guida
    exit /b 0
)
echo Opzione sconosciuta: %1
exit /b 1

:continue

REM Visualizza le informazioni sull'avvio
echo Avvio server di discovery su %BIND%:%PORT%...

REM Attiva l'ambiente virtuale se esiste
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Esegui il server di discovery
python meshnet\discovery\discovery_server.py --port %PORT% --bind %BIND% 