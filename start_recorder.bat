@echo off
rem Ascend InQ auto recorder: records each game, then builds the review viewer.
cd /d "%~dp0"
title Ascend InQ recorder
python review.py record --open
pause
