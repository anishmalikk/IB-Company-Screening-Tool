from fastapi import FastAPI
from pydantic import BaseModel
from exec_scraper import get_exec_info, search_linkedin

app = FastAPI()

class ScreenRequest(BaseModel):
    ticker: str

@app.post("/screen")
def screen_company(req: ScreenRequest):
    execs = get_exec_info(req.ticker)

    enriched_execs = {}
    for title, name in execs.items():
        if name != "Not Found":
            profile = search_linkedin(name, req.ticker)
            enriched_execs[title] = {
                "name": name,
                "linkedin": profile["linkedin"],
                "email": profile["email"]
            }
        else:
            enriched_execs[title] = {
                "name": "Not Found",
                "linkedin": "",
                "email": ""
            }

    return {
        "message": f"Screening {req.ticker}...",
        "executives": enriched_execs
    }
