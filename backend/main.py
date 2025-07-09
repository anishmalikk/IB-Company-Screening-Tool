from fastapi import FastAPI
from exec_scraper import get_execs_via_serp

app = FastAPI()

@app.get("/execs/{company_name}")
def read_executives(company_name: str):
    return {"executives": get_execs_via_serp(company_name)}
