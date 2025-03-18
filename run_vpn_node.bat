@echo off
REM Script per avviare un nodo VPN nella rete mesh su Windows
REM Richiede privilegi di amministratore per creare l'interfaccia TUN

REM Verifica privilegi di amministratore
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Sono richiesti privilegi di amministratore per creare interfacce TUN/TAP.
    echo Per favore esegui come amministratore (tasto destro sul file, "Esegui come amministratore")
    pause
    exit /b 1
)

REM Impostazioni predefinite
set SERVER=127.0.0.1:8000
set NODE_ID=
set PORT=0
set TUN_ADDRESS=10.0.0.0
set NETWORK=10.0.0.0/24
set KEY=

REM Parsing parametri
:loop
if "%1"=="" goto :continue
if "%1"=="--server" (
    set SERVER=%2
    shift
    shift
    goto :loop
)
if "%1"=="--id" (
    set NODE_ID=%2
    shift
    shift
    goto :loop
)
if "%1"=="--port" (
    set PORT=%2
    shift
    shift
    goto :loop
)
if "%1"=="--tun" (
    set TUN_ADDRESS=%2
    shift
    shift
    goto :loop
)
if "%1"=="--network" (
    set NETWORK=%2
    shift
    shift
    goto :loop
)
if "%1"=="--key" (
    set KEY=%2
    shift
    shift
    goto :loop
)
if "%1"=="--help" (
    echo Utilizzo: %0 [opzioni]
    echo Opzioni:
    echo   --server INDIRIZZO   Server di scoperta (default: %SERVER%)
    echo   --id ID              ID nodo (default: generato automaticamente)
    echo   --port PORTA         Porta UDP locale (default: %PORT%, 0=automatica)
    echo   --tun INDIRIZZO      Indirizzo IP dell'interfaccia TUN (default: %TUN_ADDRESS%)
    echo   --network RETE       Rete VPN (CIDR, default: %NETWORK%)
    echo   --key CHIAVE         Chiave di cifratura (default: generata automaticamente)
    echo   --help               Mostra questa guida
    exit /b 0
)
echo Opzione sconosciuta: %1
exit /b 1

:continue

REM Attiva l'ambiente virtuale se esiste
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Genera una chiave se non specificata
if "%KEY%"=="" (
    echo Nessuna chiave specificata, genero una chiave casuale...
    
    REM Verifica se PyNaCl è installato
    python -c "import nacl.utils" >nul 2>&1
    if %errorLevel% neq 0 (
        echo Errore: PyNaCl è richiesto per generare la chiave
        echo Installa con: pip install pynacl
        pause
        exit /b 1
    )
    
    REM Genera chiave con Python e nacl
    for /f "delims=" %%i in ('python -c "import nacl.utils, binascii; print(binascii.hexlify(nacl.utils.random(32)).decode())"') do set KEY=%%i
    echo Chiave generata: %KEY%
)

REM Info
echo Avvio nodo VPN mesh...
echo Server di scoperta: %SERVER%
echo Rete: %NETWORK%
echo Chiave: %KEY%

REM Costruisci il comando
set CMD=python meshnet\core\vpn_node.py --server %SERVER% --port %PORT% --network %NETWORK% --key %KEY%
if not "%NODE_ID%"=="" (
    set CMD=%CMD% --id %NODE_ID%
)
if not "%TUN_ADDRESS%"=="" (
    set CMD=%CMD% --tun %TUN_ADDRESS%
)

echo Esecuzione: %CMD%
%CMD% 