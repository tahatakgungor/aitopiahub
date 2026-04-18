import os
import paramiko
from scp import SCPClient
from dotenv import load_dotenv

def deploy():
    # Load settings from local .env
    load_dotenv()

    host = os.getenv("VPS_HOST")
    user = os.getenv("VPS_USER", "root")
    password = os.getenv("VPS_PASSWORD")
    remote_path = os.getenv("VPS_REMOTE_PATH", "/opt/aitopiahub")

    if not host or not password:
        print("❌ Error: VPS_HOST and VPS_PASSWORD must be set in .env")
        return

    print(f"📡 Connecting to {host} via Paramiko...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password)

    # 1. Sync files via SCP
    print("🚀 Uploading source code and configurations...")
    scp = SCPClient(ssh.get_transport())
    
    # Sync core directories
    dirs_to_sync = ["src", "configs", "docker", "assets", "scripts"]
    for d in dirs_to_sync:
        print(f"Uploading {d}...")
        try:
            scp.put(d, recursive=True, remote_path=remote_path)
        except Exception as e:
            print(f"⚠️ Upload warning for {d}: {e}")

    # Sync single files
    for f in [".env", ".env.example", "pyproject.toml", "poetry.lock", "alembic.ini"]:
        if os.path.exists(f):
            print(f"Uploading {f}...")
            scp.put(f, remote_path=remote_path)

    # 2. Docker build and restart
    print("🔄 Restarting Docker containers on VPS (Kids 7/24 mode)...")
    commands = [
        f"cd {remote_path} && docker compose -f docker/docker-compose.yml up -d --build",
        f"cd {remote_path} && chmod +x scripts/*.sh",
    ]

    if os.getenv("INSTALL_OPS_CRON", "true").lower() == "true":
        commands.append(f"cd {remote_path} && sudo bash scripts/install_ops_cron.sh")
    
    for cmd in commands:
        print(f"Execution: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        _ = stdout.channel.recv_exit_status()
        print(stdout.read().decode())
        print(stderr.read().decode())

    scp.close()
    ssh.close()
    print("✨ Deployment complete! Autonomous Kids Hub is now LIVE on server.")

if __name__ == "__main__":
    deploy()
