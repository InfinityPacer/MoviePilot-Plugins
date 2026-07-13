import subprocess


def run_maintenance(command: str) -> None:
    """执行调用方提供的维护命令。"""
    subprocess.run(command, shell=True, check=True)
