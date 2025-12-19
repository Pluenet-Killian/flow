import sys
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal
import threading

from claude import switch_branch, launch_claude_process, log_to_stderr


class ClaudeRequest(BaseModel):
    jobId: str
    branchName: str
    commitSha: str
    action: Literal['build_i4gen', 'build_compact', 'issue_detector']

app = FastAPI()


@app.get("/")
def read_root():
    return {"Server": "FastAPI is running"}


@app.post("/trigger")
def launch_claude(request: ClaudeRequest):
    if not switch_branch(request.branchName):
        return {"error": "Error switching branches"}

    log_to_stderr(f"Lancement de Claude pour la branche: {request.branchName}\n")
    log_to_stderr(f"Commit: {request.commitSha}\n")
    log_to_stderr(f"Job ID: {request.jobId}\n")
    log_to_stderr(f"Action: {request.action}\n")
    log_to_stderr("=" * 60 + "\n\n")

    thread = threading.Thread(target=launch_claude_process, args=(request, 1))
    thread.start()

    print("Claude process launched in a separate thread.\n")
    # response = "Claude process started."
    # if not response:
    #     return {"error": "Error launching Claude process"}

    return {
        "jobId": "abc12345",
        "status": "accepted",
        "message": "Job accepted"
    }
