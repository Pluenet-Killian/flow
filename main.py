from typing import Union

from fastapi import FastAPI
from pydantic import BaseModel
import asyncio

from claude import switch_branch, launch_claude_process

class Claude(BaseModel):
    branch: str
    hash: str
    link: str

app = FastAPI()

@app.get("/")
def read_root():
    return {"Server": "FastAPI is running"}

@app.post("/claude")
def launch_claude(claude: Claude):
    switch_result = switch_branch(claude.branch)
    if not switch_result:
        return {"error": "Error switching branches"}
    response = asyncio.run(launch_claude_process())
    if not response:
        return {"error": "Error launching Claude process"}
    print("Claude response:", response)
    return {
        "message": "Claude launched successfully",
        "details": {
            "branch": claude.branch,
            "hash": claude.hash,
            "link": claude.link
        }
    }
