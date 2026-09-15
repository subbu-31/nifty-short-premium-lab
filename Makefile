.PHONY: install test smoke

install:
	pip3 install -r requirements.txt

test:
	python3 -m pytest tests/ -v

# Runs the backtest engine end-to-end against a synthetic BSM-generated
# option chain, since the real NSE data isn't distributed with this repo.
# Confirms the pipeline wiring (structure -> cost -> settle) still works.
smoke:
	python3 -c "\
from pipeline.backtest.engine import price_structure_at_entry, settle; \
from pipeline.structure.black_scholes import price as bs_price; \
from pipeline.cost.cost_scenarios import CostScenario; \
S=24000.0; T=4/365.0; r=0.065; strikes=list(range(23000,25100,50)); \
chain=lambda e,x: {(k,s): bs_price(S,k,T,r,0.14,o) for k in strikes for s,o in [('CE','C'),('PE','P')] if bs_price(S,k,T,r,0.14,o)>0.5}; \
spot=lambda d: S; \
ticket=price_structure_at_entry('2025-01-01','2025-01-05',T,chain,spot); \
scenario=CostScenario(name='smoke',short_leg_cost=0.5,wing_leg_cost=0.3,statutory_pct=0.0006); \
print(settle(ticket, S_exit=24100.0, scenario=scenario))"
