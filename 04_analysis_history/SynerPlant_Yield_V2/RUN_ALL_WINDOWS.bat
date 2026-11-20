@echo off
REM SynerPlant Yield V2 - full reproducible rebuild (double-click). Takes ~15-25 minutes on 8 cores.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating the V2 Python environment - one time, needs Internet...
  py -3.12 -m venv .venv || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements_v2.txt
)
set PY=%~dp0.venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8
cd src
if exist "..\outputs\preregistration\PREREG_TEST_V2.json" goto :frozen
"%PY%" s01_integrity.py              || goto :err
"%PY%" s02_corrections.py            || goto :err
"%PY%" s01_integrity.py              || goto :err
"%PY%" s03_build_dataset.py          || goto :err
"%PY%" s03b_physiology_feasibility.py || goto :err
"%PY%" s04_train.py                  || goto :err
"%PY%" s05_evaluate.py               || goto :err
"%PY%" s05b_importance.py            || goto :err
"%PY%" s06_uncertainty.py            || goto :err
"%PY%" s07_meta.py                   || goto :err
"%PY%" s08_audit_package.py          || goto :err
"%PY%" s10_final_model.py            || goto :err
"%PY%" s09_figures.py                || goto :err
"%PY%" s11_freeze.py                 || goto :err
echo.
echo ALL STEPS FINISHED. Open the dashboard with OPEN_DASHBOARD_WINDOWS.bat
pause
exit /b 0
:err
echo.
echo A STEP FAILED - see the message above. Nothing was deleted.
pause
exit /b 1
:frozen
echo.
echo The TEST analysis is PRE-REGISTERED: the V2 model, data and freeze are locked and are NOT rebuilt.
echo Checking that every pre-registered file is unchanged...
"%PY%" s13_test_evaluation.py --verify-only
if exist "..\outputs\preregistration\ADDENDUM_1_TEST.json" "%PY%" s12b_addendum.py --verify
echo To evaluate the TEST once, see outputs\preregistration\PREREG_TEST_V2.md and ADDENDUM_1_TEST.md
pause
exit /b 0
