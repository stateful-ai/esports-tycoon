import sys
import time
import subprocess
import webbrowser
import socket
from pathlib import Path

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    repo_root = Path(__file__).resolve().parents[1]
    venv_python = repo_root / ".venv-win" / "Scripts" / "python.exe"
    
    if not venv_python.exists():
        print(f"Error: Virtual environment python not found at: {venv_python}")
        sys.exit(1)
        
    port = 8420
    url = f"http://127.0.0.1:{port}/map-studio.html"
    
    print("=" * 60)
    print("                ESPORTS SIMULATOR - MAP STUDIO               ")
    print("=" * 60)
    
    # If port is already in use, check if it is our server
    server_already_running = is_port_in_use(port)
    
    if server_already_running:
        print(f"Server is already running on port {port}.")
        print(f"Opening editor: {url}")
        webbrowser.open(url)
        print("=" * 60)
        return
        
    print(f"Starting server on port {port}...")
    
    # Launch uvicorn server in background
    cmd = [
        str(venv_python),
        "-m", "esports_sim",
        "--web",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--no-browser"
    ]
    
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for port to open
        print("Waiting for server to initialize...")
        for _ in range(10):
            time.sleep(0.5)
            if is_port_in_use(port):
                break
        else:
            print("Warning: Server took too long to start, attempting to open browser anyway.")
            
        print(f"Opening browser to: {url}")
        webbrowser.open(url)
        
        print("\nMap Studio is active and running.")
        print("Keep this window open while using the Map Studio.")
        print("Press Ctrl+C to shut down the server.")
        print("=" * 60)
        
        # Keep process alive and wait for interruption
        while True:
            time.sleep(1.0)
            if process.poll() is not None:
                print("\nServer process terminated unexpectedly.")
                break
                
    except KeyboardInterrupt:
        print("\nShutting down Map Studio server...")
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
        print("Goodbye!")

if __name__ == "__main__":
    main()
