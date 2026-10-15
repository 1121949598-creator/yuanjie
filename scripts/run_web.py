"""Run the Vue UI with the supplied backend; optional trusted ScanCode executable."""
import argparse
import os
from pathlib import Path

import uvicorn
from yuanjian_agent.config import Settings, ScannerSettings, LicenseProviderSettings
from yuanjian_agent.web import create_app

def resolve_scancode_executable(configured: str | None) -> Path | None:
    """Only discover the host-managed tool, never binaries from scanned sources."""
    if configured:
        return Path(configured).resolve()
    root = Path(__file__).resolve().parents[1]
    local = root / '.tools' / 'scancode-venv' / ('Scripts/scancode.exe' if os.name == 'nt' else 'bin/scancode')
    return local if local.is_file() else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data-dir', default=str(Path(__file__).resolve().parents[1] / '.local-data'))
    parser.add_argument('--scancode', default=os.getenv('YUANJIAN_SCANCODE_EXE'))
    args = parser.parse_args()
    settings = Settings(data_dir=Path(args.data_dir).resolve(), demo_mode=True)
    executable = resolve_scancode_executable(args.scancode)
    if executable:
        if not executable.is_file():
            parser.error('ScanCode executable does not exist')
        settings.scanners = ScannerSettings(enable_scancode=True)
        settings.license_providers = LicenseProviderSettings(scancode_executable=executable,scancode_version='32.5.0',timeout_seconds=300,probe_timeout_seconds=30)
    share_password = os.getenv('YUANJIAN_SHARE_PASSWORD')
    if share_password and len(share_password) < 12:
        parser.error('YUANJIAN_SHARE_PASSWORD must contain at least 12 characters')
    print(f'源界 UI: http://127.0.0.1:{args.port}/app/', flush=True)
    if share_password:
        print('Shared preview authentication enabled (username: yuanjian)', flush=True)
    uvicorn.run(create_app(settings, share_password=share_password), host='127.0.0.1', port=args.port)

if __name__ == '__main__':
    main()
