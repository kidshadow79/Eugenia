@echo off
chcp 65001 >nul
echo ===================================================
echo   Installation de l'environnement EUGENIA (venv)
echo ===================================================
echo.

cd /d %~dp0

:: Vérifier si Python est installé
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python n'est pas détecté sur votre système.
    echo Tentative d'installation automatique de Python 3.11 via Windows Package Manager (winget)...
    echo.
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo Installation de Python en cours, veuillez patienter...
        winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        if %errorlevel% equ 0 (
            echo.
            echo [SUCCÈS] Python a été installé avec succès !
            echo IMPORTANT : Veuillez fermer cette fenêtre et relancer install.bat
            echo afin que le système prenne en compte le nouveau PATH Python.
            pause
            exit /b 0
        )
    )
    echo [ERREUR] Python n'est pas installe et winget n'a pas pu l'installer automatiquement.
    echo Veuillez installer Python 3.10+ manuellement (https://www.python.org/downloads/)
    echo et cocher la case "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)

:: Créer l'environnement virtuel si inexistant
if not exist venv (
    echo [1/3] Creation de l'environnement virtuel (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERREUR] Impossible de creer le venv.
        pause
        exit /b 1
    )
) else (
    echo [1/3] L'environnement virtuel (venv) existe deja.
)

:: Activer le venv et installer les dépendances
echo [2/3] Activation du venv et mise a jour de pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1

echo [3/3] Installation des dependances depuis requirements.txt...
pip install -r requirements.txt

echo.
echo ===================================================
echo   Installation terminee avec succes !
echo   Vous pouvez maintenant lancer EUGENIA avec run.bat
echo ===================================================
pause
