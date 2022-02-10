@echo off

set ADDON_DIR=C:\tmp
set VERSION=0.9.0

call env.bat

if "%1"=="" (
    exit
)

if "%1"=="build" (
    rd /s /q "%ADDON_DIR%\texture_bake" >NUL 2>&1
    xcopy /q /i /s .\source "%ADDON_DIR%\texture_bake" >NUL 2>&1
    xcopy /q .\*.md "%ADDON_DIR%\texture_bake" >NUL 2>&1
    exit
)

if "%1"=="package" (
    rd /s /q .\out >NUL 2>&1
    mkdir .\out >NUL 2>&1
    xcopy /q /i /s .\source .\out\texture_bake >NUL 2>&1
    xcopy /q .\*.md .\out\texture_bake >NUL 2>&1
    cd .\out
    tar -acf texture-bake_%VERSION%.zip texture_bake
    cd ..
    exit
)
