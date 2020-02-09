@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x86
SET SELF_PATH=%~dp0%
SET CXX=
SET CC=
echo BUILDER_PATH = %SELF_PATH%
cd sourcemod && python %SELF_PATH:~0,-1%\..\build.py