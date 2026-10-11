import importlib.util
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location('logger',root/'scripts/playtest_log.py')
logger=importlib.util.module_from_spec(spec)
spec.loader.exec_module(logger)
logger.LOG_DIR=root/'docs/playtests/2026-10-11-flavor-served-title'
logger.main()
