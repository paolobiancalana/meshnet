@echo off
REM Script per configurare l'ambiente di sviluppo su Windows

echo =============================================
echo  Configurazione ambiente MeshNet per Windows
echo =============================================

REM Verifica Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Python non trovato! Installa Python 3.8 o superiore.
    echo Scarica da: https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

REM Verifica virtualenv
python -m pip show virtualenv >nul 2>&1
if %errorLevel% neq 0 (
    echo Installazione di virtualenv...
    python -m pip install virtualenv
)

REM Crea ambiente virtuale se non esiste
if not exist venv\ (
    echo Creazione ambiente virtuale...
    python -m virtualenv venv
) else (
    echo Ambiente virtuale già esistente.
)

REM Attiva l'ambiente virtuale
call venv\Scripts\activate.bat

REM Installa dipendenze
echo Installazione dipendenze...
pip install pynacl cryptography flask pyroute2 pytest pytest-cov

REM Verifica che TAP-Windows sia installato (richiesto per l'interfaccia TUN/TAP)
echo.
echo IMPORTANTE: Assicurati di aver installato il driver TAP-Windows
echo È disponibile come parte di OpenVPN o come pacchetto separato.
echo Scarica OpenVPN da: https://openvpn.net/community-downloads/
echo.

REM Crea un file di configurazione di esempio
if not exist config.local.ini (
    echo Creazione file di configurazione di esempio...
    echo [discovery]> config.local.ini
    echo port = 8000>> config.local.ini
    echo bind = 0.0.0.0>> config.local.ini
    echo [vpn]>> config.local.ini
    echo network = 10.0.0.0/24>> config.local.ini
)

echo.
echo Configurazione completata!
echo.
echo Per avviare il server di discovery: run_discovery_server.bat
echo Per avviare un nodo VPN: run_vpn_node.bat (come amministratore)
echo.

pause 