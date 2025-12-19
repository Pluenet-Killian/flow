import sys
from fastapi import FastAPI
from pydantic import BaseModel

from claude import switch_branch, launch_claude_process, log_to_stderr


class ClaudeRequest(BaseModel):
    jobId: str
    branchName: str
    commitSha: str
    action: str

app = FastAPI()


@app.get("/")
def read_root():
    return {"Server": "FastAPI is running"}


@app.post("/trigger")
def launch_claude(request: ClaudeRequest):
    if not switch_branch(request.branchName):
        return {"error": "Error switching branches"}

    # log_to_stderr(f"Lancement de Claude pour la branche: {request.branchName}\n")
    # log_to_stderr(f"Commit: {request.commitSha}\n")
    # log_to_stderr(f"Job ID: {request.jobId}\n")
    # log_to_stderr(f"Action: {request.action}\n")
    # log_to_stderr("=" * 60 + "\n\n")

    # response = launch_claude_process(
    #     request,
    #     verbosity=1  # 0=minimal, 1=normal (tools), 2=debug JSON
    # )

    # if not response:
    #     return {"error": "Error launching Claude process"}

    return {
        "message": "Claude launched successfully",
        # "response": response,
        # "details": {
        #     "branch": request.branch,
        #     "hash": request.hash,
        #     "link": request.link
        # }
    }
