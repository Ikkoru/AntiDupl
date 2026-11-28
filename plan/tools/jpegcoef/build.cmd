@echo off
rem Builds jpegcoef.exe into the folder given (default: this folder's bin\,
rem which git ignores) with MSVC toolset v143 and vcpkg's static
rem libjpeg-turbo: the x64-windows-static triplet installed under the vcpkg
rem folder that VCPKG_ROOT names (vcpkg install libjpeg-turbo:x64-windows-static).
setlocal
set "HERE=%~dp0"
set "OUT=%~1"
if "%OUT%"=="" set "OUT=%HERE%bin"
if not exist "%OUT%" mkdir "%OUT%"
rem The output folder holds only what this builds: marked as a cache, so
rem backups skip it and it may be deleted.
if not exist "%OUT%\CACHEDIR.TAG" (echo Signature: 8a477f597d28d172789f06886806bc55& echo # jpegcoef build output, rebuilt by build.cmd) > "%OUT%\CACHEDIR.TAG"
if not defined VCPKG_ROOT (echo Set VCPKG_ROOT to the vcpkg folder.& exit /b 1)
set "VCPKG_LIB=%VCPKG_ROOT%\installed\x64-windows-static"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VS="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property installationPath`) do set "VS=%%i"
if not defined VS exit /b 1
rem vcvars64.bat runs vswhere itself and expects it on PATH.
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" -vcvars_ver=14.44 >nul || exit /b 1
cl /nologo /O2 /MT /W3 /D_CRT_SECURE_NO_WARNINGS /I "%VCPKG_LIB%\include" "%HERE%jpegcoef.c" /Fo"%OUT%\\" /Fe"%OUT%\jpegcoef.exe" /link "%VCPKG_LIB%\lib\jpeg.lib" || exit /b 1
