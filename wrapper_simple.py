# -*- coding: utf-8 -*-
"""
wrapper_simple.py for the PJM/EIC simple DCOPF workflow.

Adjusted for the raw-generator outage-capacity workflow:
- EICDataSetup is expected to load HorizonGenLimits_base_{NN}_y_{YEAR}.csv
  and HorizonMustrunLimits_base_{NN}_y_{YEAR}.csv into EIC_data.dat as
  SimGenLimit and SimMustrunLimit.
- This wrapper only transfers those already outage-adjusted annual limits
  into the 24-hour horizon parameters.
- It does not read east*_lostcap_v4.csv, does not load df_dict2_*.npy, and
  does not subtract GADS category lost-capacity values a second time.
"""

from pyomo.opt import SolverFactory
from EIC_simple import model as m1
from pyomo.core import Var
from pyomo.core import Constraint
#from pyomo.core import Param
#from operator import itemgetter
import pandas as pd, glob
import numpy as np
import os
import re
from pathlib import Path
#from datetime import datetime
import pyomo.environ as pyo
#from pyomo.environ import value
import argparse
import logging

print("buses defined?", hasattr(m1, "buses"))

logging.getLogger('pyomo.core').setLevel(logging.ERROR)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--win",
    type=int,
    choices=range(4),
    default=0,      # ← here’s your default window
    help="which 0–3 window to solve (defaults to 0)",
)
args = parser.parse_args()
win = args.win

#days = 365 # Max = 365

solve_windows = [(  1, 100),          # start day, length (days)
                 (101, 100),
                 (201, 100),
                 (301,  65)]
win_start, win_len = solve_windows[args.win]

win_end = win_start + win_len - 1
out_suffix = f"win{win}"         # e.g., win2_201-300

instance = m1.create_instance('EIC_data.dat')
instance.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

Solvername = 'gurobi'
Timelimit = 14400 # for the simulation of one day in seconds
#Timelimit = 7200 # for the simulation of one day in seconds
Threadlimit = 2 # maximum number of threads to use

opt = SolverFactory(Solvername)
if Solvername == 'cplex':
    opt.options['timelimit'] = Timelimit
elif Solvername == 'gurobi':           
    opt.options['TimeLimit'] = Timelimit
    opt.options['DualReductions'] = 0
    #opt.options['MIPFocus'] = 1  # Focus on finding a feasible solution
    
opt.options['threads'] = Threadlimit

H = instance.HorizonHours
D = 2
K=range(1,H+1)


def _safe_get_param(param_obj, key, default=0.0):
    """Safely read a Pyomo indexed parameter, returning default when missing."""
    try:
        if key in param_obj:
            return pyo.value(param_obj[key])
    except Exception:
        pass
    try:
        return pyo.value(param_obj[key])
    except Exception:
        return default



#Space to store results
mwh=[]
on=[]
switch=[]
flow=[]
# srsv=[]
# nrsv=[]
slack = []
vlt_angle=[]
duals=[]
objective_values = []

cwd = Path.cwd()
base_dir = cwd.parent / "Data"
data_allocation_dir = base_dir / "data_allocation"

# infer NN (number of nodes) from this folder’s name, e.g. "Exp500_simple_300_1"
folder = Path.cwd().name
m = re.match(r'^Exp(\d+)', folder)
if not m:
    raise RuntimeError(f"Could not infer NN from folder name '{folder}'")
NN = int(m.group(1))
#parts = folder.split('_')            # ["Exp500", "simple", "300", "1"]
#UC      = parts[0].replace(f"Exp{NN}", "")   # yields "simple"
#TP      = int(parts[2])                     # 300
#SECTION = int(parts[3])                     # 1

parts = folder.split('_')
# parts == ["Exp500","simple","300"] or ["Exp500","simple","MW","100"]
UC = parts[1]                                 # still "simple"
# if you see the literal "MW", take the next token; otherwise treat parts[2] as percent
if parts[2].upper() == 'MW':
    TP = int(parts[3])                       # additive‑MW experiment
else:
    TP = int(parts[2])                       # old “percent” experiment

def _infer_year_from_exp_folder(folder_name: str) -> int:
    """
    Infer simulation year from Exp folder name.

    Expected examples:
        Exp500_simple_-30_2016
        Exp500_simple_0_2019
        Exp500_simple_MW_100_2019
    """
    m = re.search(r'_(\d{4})$', folder_name)
    if not m:
        raise RuntimeError(
            f"Could not infer year from folder name '{folder_name}'. "
            "Expected folder name to end with _YYYY."
        )
    return int(m.group(1))

YEAR = _infer_year_from_exp_folder(folder)

df_generators = pd.read_csv(os.path.join(data_allocation_dir, f'data_genparams_{NN}.csv'), header=0)

# Outage-adjusted generator limits
# The updated allocation/DataSetup workflow now prepares raw-generator-based
# available-capacity limits before the wrapper runs:
#   SimGenLimit[j, hour]        -> dispatchable thermal available capacity
#   SimMustrunLimit[bus, hour]  -> nuclear/must-run available capacity
# Therefore, do NOT read east*_lostcap_v4.csv or subtract category-level
# lost capacity again in this wrapper.

if not (hasattr(instance, "SimGenLimit") and hasattr(instance, "HorizonGenLimit")):
    raise RuntimeError(
        "Model/data mismatch: EIC_simple.py/EIC_data.dat must define "
        "SimGenLimit and HorizonGenLimit."
    )

if not (hasattr(instance, "SimMustrunLimit") and hasattr(instance, "HorizonMustrunLimit")):
    raise RuntimeError(
        "Model/data mismatch: EIC_simple.py/EIC_data.dat must define "
        "SimMustrunLimit and HorizonMustrunLimit."
    )

print(
    f"Using outage-adjusted SimGenLimit and SimMustrunLimit from EIC_data.dat "
    f"for NN={NN}, YEAR={YEAR}."
)

#len(instance.InternalBuses)
#len(instance.Exchange)
len(instance.buses)

#max here can be (1,365)
for day in range(win_start, win_start + win_len):
#for day in range(1, 3):
#for day in range(1,days+1):
     
    print(f"\n=== Solving day {day} of window {win_start}-{win_start+win_len-1}")
    
    for z in instance.buses:
    #load Demand and Reserve time series data
        for i in K:
            instance.HorizonDemand[z,i] = instance.SimDemand[z,(day-1)*24+i]

            # instance.HorizonReserves[i] = instance.SimReserves[(day-1)*24+i]

    for z in instance.Hydro:
    #load Hydropower time series data
        if (z, day) in instance.SimHydro:
            instance.HorizonHydro[z] = instance.SimHydro[z, day]
        else:
            instance.HorizonHydro[z] = 0.0
        
    for z in instance.Solar:
    #load Solar time series data
        for i in K:
            t_idx = (day-1)*24 + i
            if (z, t_idx) in instance.SimSolar:
                instance.HorizonSolar[z, i] = instance.SimSolar[z, t_idx]
            else:
                instance.HorizonSolar[z, i] = 0.0

    for z in instance.Wind:
    #load Wind time series data
        for i in K:
            t_idx = (day-1)*24 + i
            if (z, t_idx) in instance.SimWind:
                instance.HorizonWind[z, i] = instance.SimWind[z, t_idx]
            else:
                instance.HorizonWind[z, i] = 0.0
            
    for z in instance.Thermal:
    #load fuel prices for thermal generators
        instance.FuelPrice[z] = instance.SimFuelPrice[z,day]
        
    # Organizing outage data
    # Load already outage-adjusted gen and must-run capacity time series.
    # These values were produced from raw/pre-reduction generator available
    # capacity and written into EIC_data.dat by EICDataSetup.
    for z in instance.Outage:
        base_cap = None
        try:
            if hasattr(instance, "maxcap") and z in instance.maxcap:
                base_cap = float(pyo.value(instance.maxcap[z]))
        except Exception:
            base_cap = None

        for i in K:
            t_idx = (day - 1) * 24 + i
            val = float(_safe_get_param(instance.SimGenLimit, (z, t_idx), default=0.0))
            if base_cap is not None:
                val = min(base_cap, val)
            instance.HorizonGenLimit[z, i] = max(0.0, val)

    for z in instance.buses:
        for i in K:
            t_idx = (day - 1) * 24 + i
            val = float(_safe_get_param(instance.SimMustrunLimit, (z, t_idx), default=0.0))
            instance.HorizonMustrunLimit[z, i] = max(0.0, val)

# =============================================================================
#     
#     result = opt.solve(instance,tee=True,symbolic_solver_labels=True, load_solutions=False) ##,tee=True to check number of variables\n",
#     #instance.solutions.load_from(result)  
#     
#     # Check the solver status before loading the solution
#     if result.solver.status == pyo.SolverStatus.ok and (result.solver.termination_condition == pyo.TerminationCondition.optimal or result.solver.termination_condition == pyo.TerminationCondition.feasible):
#         instance.solutions.load_from(result)
#     else:
#         print("The solver did not find a feasible solution.")
#         # Handle this situation (e.g., try a different approach, log the error, etc.)
#         
# =============================================================================

    # Solver execution and checking for feasible solutions
    result = opt.solve(instance, tee=True, symbolic_solver_labels=True, load_solutions=False)
    
    if result.solver.status == pyo.SolverStatus.ok and (
        result.solver.termination_condition == pyo.TerminationCondition.optimal or
        result.solver.termination_condition == pyo.TerminationCondition.feasible):
        
        # Load the solution into the instance
        instance.solutions.load_from(result)
    
        # Get and store the objective value in the parameter
        instance.ObjValue = pyo.value(instance.SystemCost)
        print(f"Objective Value for Day {day}: {instance.ObjValue}")
    
        # Store the day and objective value in a list for tracking
        objective_values.append((day, instance.ObjValue))
    else:
        print("The solver did not find a feasible solution.")

    print('LP')

    for c in instance.component_objects(Constraint, active=True):
        cobject = getattr(instance, str(c))
        if str(c) in ['Node_Constraint']:
            for index in cobject:
                 if int(index[1]>0 and index[1]<25):
                     try:
                         duals.append((index[0],index[1]+((day-1)*24), instance.dual[cobject[index]]))
                     except KeyError:
                         duals.append((index[0],index[1]+((day-1)*24),-999))

    for v in instance.component_objects(Var, active=True):
        varobject = getattr(instance, str(v))
        a=str(v)
                  
        if a=='Theta':
            for index in varobject:
                if int(index[1]>0 and index[1]<25):
                    if index[0] in instance.buses:
                        vlt_angle.append((index[0],index[1]+((day-1)*24),varobject[index].value))
                        
        if a=='mwh':
            for index in varobject:
                
                gen_name = index[0]
                gen_heatrate = df_generators[df_generators['name']==gen_name]['heat_rate'].values[0]
                
                if int(index[1]>0 and index[1]<25):
                    
                    # fuel_price = instance.FuelPrice[z].value
                    
                    if index[0] in instance.Gas:
                        # marginal_cost = gen_heatrate*fuel_price
                        mwh.append((index[0],'Gas',index[1]+((day-1)*24),varobject[index].value))   
                    elif index[0] in instance.Coal:
                        # marginal_cost = gen_heatrate*fuel_price
                        mwh.append((index[0],'Coal',index[1]+((day-1)*24),varobject[index].value))  
                    elif index[0] in instance.Oil:
                        # marginal_cost = 0
                        mwh.append((index[0],'Oil',index[1]+((day-1)*24),varobject[index].value))   
                    elif index[0] in instance.Hydro:
                        # marginal_cost = 0
                        mwh.append((index[0],'Hydro',index[1]+((day-1)*24),varobject[index].value)) 
                    elif index[0] in instance.Solar:
                        # marginal_cost = 0
                        mwh.append((index[0],'Solar',index[1]+((day-1)*24),varobject[index].value))
                    elif index[0] in instance.Wind:
                        # marginal_cost = 0
                        mwh.append((index[0],'Wind',index[1]+((day-1)*24),varobject[index].value))                                            
        
        if a=='on':  
            for index in varobject:
                if int(index[1]>0 and index[1]<25):
                    on.append((index[0],index[1]+((day-1)*24),varobject[index].value))

        if a=='switch':
            for index in varobject:
                if int(index[1]>0 and index[1]<25):
                    switch.append((index[0],index[1]+((day-1)*24),varobject[index].value))
                    
        if a=='S':    
            for index in varobject:
                if index[0] in instance.buses:
                        slack.append((index[0],index[1]+((day-1)*24),varobject[index].value))

        if a=='Flow':    
            for index in varobject:
                if int(index[1]>0 and index[1]<25):
                    flow.append((index[0],index[1]+((day-1)*24),varobject[index].value))                                            

        # if a=='srsv':    
        #     for index in varobject:
        #         if int(index[1]>0 and index[1]<25):
        #             srsv.append((index[0],index[1]+((day-1)*24),varobject[index].value))

        # if a=='nrsv':    
        #     for index in varobject:
        #         if int(index[1]>0 and index[1]<25):
        #             nrsv.append((index[0],index[1]+((day-1)*24),varobject[index].value))
        
                                
        for j in instance.Dispatchable:
            if instance.mwh[j,24].value <=0 and instance.mwh[j,24].value>= -0.0001:
                newval_1=0
            else:
                newval_1=instance.mwh[j,24].value
            instance.mwh[j,0] = newval_1
            instance.mwh[j,0].fixed = True
            


    print(day)


vlt_angle_pd=pd.DataFrame(vlt_angle,columns=('Node','Time','Value'))
mwh_pd=pd.DataFrame(mwh,columns=('Generator','Type','Time','Value'))
#on_pd=pd.DataFrame(on,columns=('Generator','Time','Value'))
#switch_pd=pd.DataFrame(switch,columns=('Generator','Time','Value'))
#srsv_pd=pd.DataFrame(srsv,columns=('Generator','Time','Value'))
#nrsv_pd=pd.DataFrame(nrsv,columns=('Generator','Time','Value'))
slack_pd = pd.DataFrame(slack,columns=('Node','Time','Value'))
flow_pd = pd.DataFrame(flow,columns=('Line','Time','Value'))
duals_pd = pd.DataFrame(duals,columns=['Bus','Time','Value'])

#to save outputs
mwh_pd.to_csv(f'mwh_{out_suffix}.csv', index=False)
vlt_angle_pd.to_csv(f'vlt_angle_{out_suffix}.csv', index=False)
#on_pd.to_csv('on.csv', index=False)
#switch_pd.to_csv('switch.csv', index=False)
#srsv_pd.to_csv('srsv.csv', index=False)
#nrsv_pd.to_csv('nrsv.csv', index=False)
slack_pd.to_csv(f'slack_{out_suffix}.csv', index=False)
flow_pd.to_csv(f'flow_{out_suffix}.csv', index=False)
duals_pd.to_csv(f'duals_{out_suffix}.csv', index=False)

# Convert the objective values to a DataFrame and save them
df_objective = pd.DataFrame(objective_values, columns=['Day', 'ObjectiveValue'])
df_objective.to_csv(f'objective_values_{out_suffix}.csv', index=False)



# =============================================================================
# 
# # Build dataframes (as you already do)
# vlt_angle_pd = pd.DataFrame(vlt_angle, columns=('Node','Time','Value'))
# mwh_pd       = pd.DataFrame(mwh,       columns=('Generator','Type','Time','Value'))
# slack_pd     = pd.DataFrame(slack,     columns=('Node','Time','Value'))
# flow_pd      = pd.DataFrame(flow,      columns=('Line','Time','Value'))
# duals_pd     = pd.DataFrame(duals,     columns=['Bus','Time','Value'])
# df_objective = pd.DataFrame(objective_values, columns=['Day', 'ObjectiveValue'])
# 
# def _safe_write(df, path):
#     tmp = Path(str(path) + ".tmp")
#     df.to_csv(tmp, index=False)
#     os.replace(tmp, path)  # atomic on POSIX; safe enough on most systems
# 
# _safe_write(mwh_pd,       outdir / 'mwh.csv')
# _safe_write(vlt_angle_pd, outdir / 'vlt_angle.csv')
# _safe_write(slack_pd,     outdir / 'slack.csv')
# _safe_write(flow_pd,      outdir / 'flow.csv')
# _safe_write(duals_pd,     outdir / 'duals.csv')
# _safe_write(df_objective, outdir / 'objective_values.csv')
# 
# 
# =============================================================================
