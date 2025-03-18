@echo off
REM MeshNet VPN - Script di avvio principale per Windows
REM Questo script verifica la disponibilità di Docker, installa una versione portable se necessario
REM e avvia i componenti di MeshNet VPN.

setlocal enabledelayedexpansion

REM Colori per output
set "HEADER=[101;93m"
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

REM Variabili
set "SCRIPT_DIR=%~dp0"
set "DOCKER_DIR=%SCRIPT_DIR%tools\docker-portable"
set "DOCKER_VERSION=20.10.21"
set "USING_PORTABLE=false"

REM Log funzioni
:log_info
    echo %BLUE%[INFO]%NC% %~1
    exit /b

:log_success
    echo %GREEN%[OK]%NC% %~1
    exit /b

:log_warning
    echo %YELLOW%[WARN]%NC% %~1
    exit /b

:log_error
    echo %RED%[ERROR]%NC% %~1
    exit /b

REM Banner
:show_banner
    echo %BLUE%
    echo ==================================================
    echo            MeshNet VPN - Avvio Sistema           
    echo ==================================================
    echo %NC%
    exit /b

REM Verifica requisiti
:check_requirements
    call :log_info "Verifico requisiti di sistema..."
    
    REM Verifica sistema operativo Windows
    ver | findstr /i "Windows" > nul
    if errorlevel 1 (
        call :log_error "Sistema operativo non supportato, richiesto Windows"
        exit /b 1
    ) else (
        call :log_info "Sistema operativo: Windows"
        set "OS_TYPE=windows"
    )
    
    REM Verifica Python
    python --version > nul 2>&1
    if errorlevel 1 (
        call :log_error "Python non trovato. Installa Python 3.8 o superiore."
        exit /b 1
    ) else (
        for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
        call :log_success "Python trovato: !PYTHON_VERSION!"
    )
    
    REM Verifica privilegi amministrativi
    net session >nul 2>&1
    if errorlevel 1 (
        call :log_warning "Questo script potrebbe richiedere privilegi di amministratore per alcune operazioni."
    )
    
    exit /b 0

REM Controlla se Docker è disponibile
:check_docker
    call :log_info "Verifico se Docker è installato..."
    
    docker info >nul 2>&1
    if errorlevel 1 (
        call :log_warning "Docker non trovato o non funzionante."
        call :log_warning "Scaricherò una versione portable di Docker."
        exit /b 1
    ) else (
        for /f "tokens=*" %%i in ('docker version --format "{{.Server.Version}}" 2^>^&1') do set "DOCKER_VERSION=%%i"
        call :log_success "Docker trovato e funzionante (versione !DOCKER_VERSION!)"
        set "DOCKER_CMD=docker"
        set "COMPOSE_CMD=docker-compose"
        exit /b 0
    )

REM Scarica e configura Docker portable per Windows
:download_docker_portable
    call :log_info "Preparazione Docker portable..."
    
    if not exist "%DOCKER_DIR%" (
        mkdir "%DOCKER_DIR%"
    )
    
    REM Scarica Docker portable per Windows
    set "DOWNLOAD_URL=https://github.com/StefanScherer/docker-cli-builder/releases/download/%DOCKER_VERSION%/docker.exe"
    
    if not exist "%DOCKER_DIR%\docker.exe" (
        call :log_info "Scarico Docker portable da !DOWNLOAD_URL!..."
        
        REM Usa PowerShell per scaricare il file
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%DOCKER_DIR%\docker.exe'}"
        
        if errorlevel 1 (
            call :log_error "Errore durante il download di Docker portable"
            exit /b 1
        )
    )
    
    REM Scarica docker-compose
    set "COMPOSE_URL=https://github.com/docker/compose/releases/download/v2.16.0/docker-compose-windows-x86_64.exe"
    
    if not exist "%DOCKER_DIR%\docker-compose.exe" (
        call :log_info "Scarico docker-compose portable..."
        
        REM Usa PowerShell per scaricare il file
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%COMPOSE_URL%' -OutFile '%DOCKER_DIR%\docker-compose.exe'}"
        
        if errorlevel 1 (
            call :log_error "Errore durante il download di docker-compose portable"
            exit /b 1
        )
    )
    
    REM Configura Docker con Docker Desktop per Windows
    call :log_info "Verifico se Docker Desktop è installato..."
    
    if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
        call :log_info "Docker Desktop trovato, utilizzo la sua configurazione"
        
        REM Usa Docker Desktop invece della versione portable
        set "DOCKER_CMD=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
        set "COMPOSE_CMD=%ProgramFiles%\Docker\Docker\resources\bin\docker-compose.exe"
    ) else (
        call :log_warning "Docker Desktop non trovato. Utilizzo la versione portable."
        call :log_info "Nota: La versione portable potrebbe richiedere un Docker Engine in esecuzione remoto."
        
        set "DOCKER_CMD=%DOCKER_DIR%\docker.exe"
        set "COMPOSE_CMD=%DOCKER_DIR%\docker-compose.exe"
        set "USING_PORTABLE=true"
        
        REM Chiedi all'utente di specificare l'host Docker remoto
        set /p DOCKER_HOST="Inserisci l'host Docker remoto (e.g., tcp://192.168.1.10:2375) o lascia vuoto per usare Docker locale: "
        
        if not "!DOCKER_HOST!" == "" (
            call :log_info "Utilizzo host Docker remoto: !DOCKER_HOST!"
            set "DOCKER_HOST_ARG=-H !DOCKER_HOST!"
        ) else (
            call :log_info "Cercherò di utilizzare Docker locale"
            set "DOCKER_HOST_ARG="
        )
    )
    
    call :log_success "Docker portable configurato correttamente"
    exit /b 0

REM Avvia il server di discovery
:start_discovery_server
    call :log_info "Avvio del server di discovery..."
    
    if "%USING_PORTABLE%" == "true" (
        "%COMPOSE_CMD%" %DOCKER_HOST_ARG% up -d discovery
    ) else (
        "%COMPOSE_CMD%" up -d discovery
    )
    
    if errorlevel 1 (
        call :log_error "Errore durante l'avvio del server di discovery"
        exit /b 1
    )
    
    call :log_success "Server di discovery avviato"
    exit /b 0

REM Avvia il nodo VPN
:start_vpn_node
    call :log_info "Avvio del nodo VPN..."
    
    set "SERVER_ADDR=127.0.0.1:8000"
    set "NODE_ID=win_node"
    
    REM Chiedi dettagli all'utente
    set /p "input=Indirizzo del server di discovery [%SERVER_ADDR%]: "
    if not "!input!" == "" set "SERVER_ADDR=!input!"
    
    set /p "input=ID del nodo [%NODE_ID%]: "
    if not "!input!" == "" set "NODE_ID=!input!"
    
    call :log_info "Avvio nodo VPN con ID %NODE_ID% connesso a %SERVER_ADDR%..."
    
    REM Verifica privilegi di amministratore per l'interfaccia TUN/TAP
    net session >nul 2>&1
    if errorlevel 1 (
        call :log_warning "Il nodo VPN richiede privilegi di amministratore per creare interfacce TUN/TAP."
        call :log_warning "Riavvia lo script come amministratore o esegui manualmente il comando:"
        echo.
        echo run_vpn_node.bat --server %SERVER_ADDR% --id %NODE_ID%
        echo.
        pause
        exit /b 1
    ) else (
        REM Esegui nodo VPN con privilegi di amministratore
        call run_vpn_node.bat --server %SERVER_ADDR% --id %NODE_ID%
    )
    
    exit /b 0

REM Ferma tutti i servizi
:stop_services
    call :log_info "Arresto dei servizi..."
    
    if "%USING_PORTABLE%" == "true" (
        "%COMPOSE_CMD%" %DOCKER_HOST_ARG% down
    ) else (
        "%COMPOSE_CMD%" down
    )
    
    call :log_success "Servizi arrestati"
    exit /b 0

REM Menu principale
:show_menu
    cls
    call :show_banner
    
    echo Menu:
    echo 1. Avvia server di discovery
    echo 2. Avvia nodo VPN
    echo 3. Avvia entrambi (server + nodo)
    echo 4. Verifica stato
    echo 5. Arresta tutti i servizi
    echo 0. Esci
    echo.
    
    set /p choice="Scegli un'opzione: "
    
    if "%choice%" == "1" (
        call :start_discovery_server
    ) else if "%choice%" == "2" (
        call :start_vpn_node
    ) else if "%choice%" == "3" (
        call :start_discovery_server
        call :start_vpn_node
    ) else if "%choice%" == "4" (
        if "%USING_PORTABLE%" == "true" (
            "%DOCKER_CMD%" %DOCKER_HOST_ARG% ps
        ) else (
            "%DOCKER_CMD%" ps
        )
    ) else if "%choice%" == "5" (
        call :stop_services
    ) else if "%choice%" == "0" (
        call :log_info "Uscita..."
        exit /b 0
    ) else (
        call :log_error "Opzione non valida"
    )
    
    pause
    goto :show_menu

REM Esecuzione principale
:main
    call :show_banner
    call :check_requirements
    
    REM Controlla Docker
    call :check_docker
    if errorlevel 1 (
        call :download_docker_portable
    )
    
    REM Mostra il menu
    call :show_menu
    
    exit /b 0

REM Avvio script
call :main
exit /b %errorlevel% 