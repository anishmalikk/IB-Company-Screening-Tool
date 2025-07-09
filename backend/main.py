
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from exec_scraper import get_execs_via_gpt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScreenInput(BaseModel):
    ticker: str
    name: str

@app.post("/screen")
def screen_company_screen_post(screen_input: ScreenInput):
    ticker = screen_input.ticker
    name = screen_input.name
    result = get_execs_via_gpt(ticker=ticker, company_name=name)
    return {"executives": result}
