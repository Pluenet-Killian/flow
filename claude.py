import subprocess
from pathlib import Path
import asyncio

def switch_branch(branch_name: str) -> bool:
    result = subprocess.run(
        ["git", "checkout", branch_name],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return False

    return True

async def launch_claude_process() -> str:
    prompt = Path(".claude/commands/analyze_py.md").read_text()

    process = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt, "--dangerously-skip-permissions",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    full_output = []
    if not process.stdout:
        return ""
    async for line in process.stdout:
        decoded = line.decode()
        print(decoded, end="")
        full_output.append(decoded)
    
    await process.wait()
    return "".join(full_output)