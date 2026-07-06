# -*- coding: utf-8 -*-
"""
Revised v2: reorder loops for efficiency while preserving behavior.
- All outputs still go to Data/data_allocation with the same filenames as v1.
- Only loop order and where computations occur were adjusted to avoid redundant work.
"""

import pandas as pd
import math
import numpy as np
import os
import xlrd
from shutil import copy
from pathlib import Path

########################################
# GLOBAL OUTPUT LOCATIONS
########################################
base_dir = 'Data'
data_allocation_dir = os.path.join(base_dir, 'data_allocation')
os.makedirs(data_allocation_dir, exist_ok=True)

# Helper to save CSVs into the new folder with a name

def _save_csv(df: pd.DataFrame, filename: str, index: bool = False):
    full = os.path.join(data_allocation_dir, filename)
    df.to_csv(full, index=index)
    return full

def _lostcap_src_for_year(base_dir: str, year) -> str:
    """
    Find the year-specific lost capacity file.

    Expected names:
        Data/Gen/east2016_lostcap_v4.csv
        Data/Gen/east2016_lostcap_v4
    """
    y = str(year)

    candidates = [
        os.path.join(base_dir, 'Gen', f'east{y}_lostcap_v4.csv'),
        os.path.join(base_dir, 'Gen', f'east{y}_lostcap_v4'),
    ]

    for p in candidates:
        if os.path.exists(p):
            return p

    raise FileNotFoundError(
        f"Could not find lost-cap file for year {y}. Checked:\n" +
        "\n".join(candidates)
    )

# Static references
#df_load = pd.read_csv('BA_load_corrected.csv',header=0, index_col=0)
df_BAs = pd.read_csv(os.path.join(base_dir, 'Interconnections/BAs_full.csv'), header=0)
BAs = list(df_BAs['Name'])

df_full = pd.read_csv(os.path.join(base_dir, 'Interconnections/nodes_to_BA_state.csv'), header=0,index_col=0)
df_full = df_full.reset_index(drop=True)
full_available = list(df_full['Number'])


#df_wind = pd.read_csv('BA_wind.csv',header=0,index_col=0)
#df_solar = pd.read_csv('BA_solar_corrected.csv',header=0,index_col=0)
df_hydro = pd.read_csv(os.path.join(base_dir, 'Gen/BA_hydro_corrected.csv'), header=0,index_col=0)

#NODE_NUMBER = [500,525,550,575,600,625,650,675,700]
NODE_NUMBER = [500]

# UC_TREATMENTS = ['_simple','_coal']
UC_TREATMENTS = ['_simple']

# trans_p = [25, 50 ,75 ,100, 200, 300, 400, 500]
#trans_p = [0, 25, 50 ,75 ,100]
trans_p = [-30, -25, -20, -15, -10, -5, 0, 25, 50, 75, 100]

#years = range(1980,2020)
years = range(2019, 2023)

for NN in NODE_NUMBER:
    FN = 'reduced_network/Results_' + str(NN) + '.xlsx'

    # Pre-read NN-specific sheets used many times
    df_selected = pd.read_excel(os.path.join(base_dir, FN), sheet_name='Bus', header=0)
    buses = list(df_selected['bus_i'])

    # Map selected nodes to BAs (NN-specific)
    selected_BAs = []
    for b in buses:
        BA = df_full.loc[df_full['Number']==b,'NAME']
        BA = BA.reset_index(drop=True)
        selected_BAs.append(BA[0])
    df_selected['BA'] = selected_BAs

    # BA totals & load weights depend only on NN; compute once
    BA_totals = []
    for b in BAs:
        sample = list(df_selected.loc[df_selected['BA']==b,'Pd'])
        corrected = [0 if x<0 else x for x in sample]
        BA_totals.append(sum(corrected))
    BA_totals = np.column_stack((BAs,BA_totals))
    df_BA_totals_load = pd.DataFrame(BA_totals, columns=['Name','Total'])

    weights = []
    for i in range(0,len(df_selected)):
        area = df_selected.loc[i,'BA']
        if df_selected.loc[i,'Pd'] <0:
            weights.append(0)
        else:
            X = float(df_BA_totals_load.loc[df_BA_totals_load['Name']==area,'Total'].iloc[0])
            W = (df_selected.loc[i,'Pd']/X)
            weights.append(W)
    df_selected['BA Load Weight'] = weights

    # Parse reduction summary once (NN-specific) for merged nodes
    df_summary = pd.read_excel(os.path.join(base_dir, FN), sheet_name='Summary', header=6)
    N = []
    merged = {}
    for i in range(0,len(df_summary)):
        test = df_summary.iloc[i,0]
        res = [int(i) for i in test.split() if i.isdigit()]
        if res[1] not in N:
            N.append(res[1])
    for n in N:
        k = []
        for i in range(0,len(df_summary)):
            test = df_summary.iloc[i,0]
            res = [int(i) for i in test.split() if i.isdigit()]
            if res[1] == n:
                k.append(res[0])
        merged[n] = k

    # ==========================
    # THERMAL GENS (NN-only)
    # ==========================
    import re
    df_gens = pd.read_csv(os.path.join(base_dir, 'Gen/Generators_EIA.csv'), header=0)
    df_gens = df_gens.replace('', np.nan, regex=True)
    df_gens_heat_rate = pd.read_csv(os.path.join(base_dir, 'Gen/Heat_rates_EIA.csv'), header=0)

    old_bus_num, new_bus_num, NB = [], [], []
    old_bus_num_hr, new_bus_num_hr, NB_hr = [], [], []
    for n in N:
        k = merged[n]
        for s in k:
            old_bus_num.append(s)
            new_bus_num.append(n)
    for i in range(0,len(df_gens)):
        OB = df_gens.loc[i,'BusNum']
        NB.append(new_bus_num[old_bus_num.index(OB)] if OB in old_bus_num else OB)
    df_gens['NewBusNum'] = NB
    for i in range(0,len(df_gens_heat_rate)):
        OB = df_gens_heat_rate.loc[i,'BusNum']
        NB_hr.append(new_bus_num[old_bus_num.index(OB)] if OB in old_bus_num else OB)
    df_gens_heat_rate['NewBusNum'] = NB_hr

    names = list(df_gens['BusName'])
    fts = list(df_gens['FuelType'])
    names_hr = list(df_gens_heat_rate['BusName'])
    fts_hr = list(df_gens_heat_rate['BusName'])
    bus_area = list(df_gens['BusAreaName'])
    bus_area_hr = list(df_gens_heat_rate['AreaName'])

    # sanitize names
    for n_ in names:
        i = names.index(n_)
        corrected = re.sub(r'[^A-Z]',r'',n_)
        f = fts[i]
        bn = bus_area[i].replace(" ", "_")
        if f == 'NUC (Nuclear)': f = 'Nuc'
        elif f == 'NG (Natural Gas)': f = 'NG'
        elif f == 'BIT (Bituminous Coal)': f = 'C'
        elif f == 'SUN (Solar)': f = 'S'
        elif f == 'WAT (Water)': f = 'H'
        elif f == 'WND (Wind)': f = 'W'
        elif f == 'DFO (Distillate Fuel Oil)': f = 'O'
        names[i] = corrected + '_' + f + '_' + bn
    for n_ in names_hr:
        i = names_hr.index(n_)
        corrected = re.sub(r'[^A-Z]',r'',n_)
        f = fts_hr[i]
        bn = bus_area_hr[i].replace(" ", "_")
        if f == 'NUC (Nuclear)': f = 'Nuc'
        elif f == 'NG (Natural Gas)': f = 'NG'
        elif f == 'BIT (Bituminous Coal)': f = 'C'
        elif f == 'SUN (Solar)': f = 'S'
        elif f == 'WAT (Water)': f = 'H'
        elif f == 'WND (Wind)': f = 'W'
        elif f == 'DFO (Distillate Fuel Oil)': f = 'O'
        names_hr[i] = corrected + '_' + f + '_' + bn

    df_gens['PlantNames'] = names
    df_gens_heat_rate['PlantNames'] = names_hr

    NB_unique = df_gens['NewBusNum'].unique()
    plants, caps, mw_min, nbs, heat_rate, f = [], [], [], [], [], []
    count = 2
    thermal = ['NG (Natural Gas)','NUC (Nuclear)','BIT (Bituminous Coal)','DFO (Distillate Fuel Oil)']

    for n_ in NB_unique:
        sample = df_gens.loc[df_gens['NewBusNum'] == n_]
        sublist = sample['PlantNames'].unique()
        for s in sublist:
            fuel = list(sample.loc[sample['PlantNames']==s,'FuelType'])
            if fuel[0] in thermal:
                c = sum(sample.loc[sample['PlantNames']==s,'MWMax'].values)
                hr = np.nanmean(sample.loc[sample['PlantNames']==s,'Heat Rate MBTU/MWh'].values)
                if hr == np.nan or hr == 0 or hr == 'nan' or hr == '':
                    hr = np.nanmean(df_gens.loc[df_gens['FuelType']==fuel[0],'Heat Rate MBTU/MWh'].values)
                mn = sum(sample.loc[sample['PlantNames']==s,'MWMin'].values)
                mw_min.append(mn)
                caps.append(c)
                nbs.append(n_)
                heat_rate.append(hr)
                f.append(fuel[0])
                if s in plants:
                    plants.append(s + '_' + str(count)); count += 1
                else:
                    plants.append(s)

    C=np.column_stack((plants,nbs,f,caps,mw_min,heat_rate))
    df_C = pd.DataFrame(C, columns=['Name','Bus','Fuel','Max_Cap','Min_Cap','Heat_Rate'])
    fn_thermal = f'thermal_gens_{NN}.csv'
    full_thermal_path = _save_csv(df_C, fn_thermal, index=False)


# =============================================================================
# 
#     # ==========================
#     # FUEL PRICES (NN-only)
#     # ==========================
#     # Build bus-level price tables
#     NG_price = pd.read_csv(os.path.join(base_dir, 'NG_price/Average_NG_prices_BAs.csv'), header=0)
#     Fuel_buses = ['bus_' + str(b) for b in buses]
#     # NG by BA per bus
#     NG_prices_all = None
#     for bus in buses:
#         selected_node_BA = df_full.loc[df_full['Number']==bus,'NAME'].values[0]
#         specific_node_NG_price = NG_price.loc[:,selected_node_BA].copy()
#         NG_prices_all = specific_node_NG_price.copy() if NG_prices_all is None else pd.concat([NG_prices_all, specific_node_NG_price], axis=1)
#     if NG_prices_all is None:
#         NG_prices_all = pd.DataFrame(columns=Fuel_buses)
#     NG_prices_all.columns = Fuel_buses
#     # Coal by state per bus
#     Coal_price = pd.read_csv(os.path.join(base_dir, 'Coal_price/coal_prices_state.csv'), header=0)
#     Coal_prices_all = None
#     for bus in buses:
#         selected_node_state = df_full.loc[df_full['Number']==bus,'STATE'].values[0]
#         if selected_node_state == 'NB': selected_node_state = 'ME'
#         elif selected_node_state == 'CO': selected_node_state = 'KS'
#         elif selected_node_state == 'OR': selected_node_state = 'AR'
#         elif selected_node_state == 'TX': selected_node_state = 'OK'
#         elif selected_node_state == 'NM': selected_node_state = 'OK'
#         elif selected_node_state == 'MT': selected_node_state = 'SD'
#         specific_node_coal_price = Coal_price.loc[:,selected_node_state].copy()
#         Coal_prices_all = specific_node_coal_price.copy() if Coal_prices_all is None else pd.concat([Coal_prices_all, specific_node_coal_price], axis=1)
#     if Coal_prices_all is None:
#         Coal_prices_all = pd.DataFrame(columns=Fuel_buses)
#     Coal_prices_all.columns = Fuel_buses
#     Oil_prices_all = pd.DataFrame({'all': np.reshape(np.ones((365,1))*20,(365,))})
# 
#     # generator-based fuel prices
#     # NOTE: genparams (used below) are year-dependent because RES capacity checks use nodal RES profiles.
#     #       Fuel prices themselves do not vary by year in this script, so we compute once per NN using buses.
#     # We'll create the mapping columns now but fill columns later when gen list is ready per year.
# 
# 
# =============================================================================


    # ==========================
    # HYDRO (NN-only; not year-specific)
    # ==========================
    # Build MWMax/FuelType mapping once
    df_gen_all = pd.read_csv(os.path.join(base_dir, 'Gen/Generators_EIA.csv'), header=0)
    MWMax = []
    fuel_type = []
    nums = list(df_gen_all['BusNum'])
    for i in range(0,len(df_full)):
        bus = df_full.loc[i,'Number']
        if bus in nums:
            MWMax.append(df_gen_all.loc[df_gen_all['BusNum']==bus,'MWMax'].values[0])
            fuel_type.append(df_gen_all.loc[df_gen_all['BusNum']==bus,'FuelType'].values[0])
        else:
            MWMax.append(0)
            fuel_type.append('none')
    df_full['MWMax'] = MWMax
    df_full['FuelType'] = fuel_type

    # BA totals (hydro) and weights once per NN
    BA_totals_h = []
    for b in BAs:
        sample = list(df_full.loc[(df_full['NAME']==b) & (df_full['FuelType'] == 'WAT (Water)'),'MWMax'])
        BA_totals_h.append(sum(sample))
    df_BA_totals_h = pd.DataFrame(np.column_stack((BAs,BA_totals_h)), columns=['Name','Total'])

    weights_h = []
    for i in range(0,len(df_full)):
        area = df_full.loc[i,'NAME']
        if str(area) in BAs and str(df_full.loc[i,'FuelType']) == 'WAT (Water)':
            X = float(df_BA_totals_h.loc[df_BA_totals_h['Name']==area,'Total'].iloc[0])
            W = (df_full.loc[i,'MWMax']/X) if X != 0 else 0
            weights_h.append(W)
        else:
            weights_h.append(0)
    df_full['BA Hydro Weight'] = weights_h

    # Nodal hydro profile (8760 x buses) using BA hydro timeseries
    buses_local = list(df_selected['bus_i'])
    T = np.zeros((8760,len(buses_local)))
    idx = 0
    for b in buses_local:
        sample = df_full.loc[df_full['Number'] == b].reset_index(drop=True)
        name = sample['NAME'][0]
        if str(name) in BAs and float(df_BA_totals_h.loc[df_BA_totals_h['Name']==str(name),'Total'].values[0]) >= 1:
            abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
            weight = sample['BA Hydro Weight'].values[0]
            T[:,idx] += np.reshape(df_hydro[abbr].values*weight,(8760,))
        try:
            m_nodes = merged[b]
            for m in m_nodes:
                sample = df_full.loc[df_full['Number'] == m].reset_index(drop=True)
                name = sample['NAME'][0]
                if str(name) in BAs and float(df_BA_totals_h.loc[df_BA_totals_h['Name']==str(name),'Total'].values[0]) >= 1:
                    abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                    weight = sample['BA Hydro Weight']
                    T[:,idx] += np.reshape(df_hydro[abbr].values*weight.values[0],(8760,))
        except KeyError:
            pass
        idx += 1
    h_buses = ['bus_' + str(b) for b in buses_local]
    df_C = pd.DataFrame(T, columns=h_buses)
    fn_hydro_out = f'nodal_hydro_{NN}.csv'
    full_hydro_path = _save_csv(df_C, fn_hydro_out)

    # precompute which reduced buses actually have wind/solar capacity based on the generator database and merging

    # After HYDRO block, before the transmission loop
    
    buses_reduced = list(df_selected['bus_i'])  # reduced-network buses
    
    # Use the generator database you already loaded as df_gen_all
    has_wind  = {b: False for b in buses_reduced}
    has_solar = {b: False for b in buses_reduced}
    
    for b in buses_reduced:
        # Original buses merged into this reduced bus
        orig_nodes = [b] + merged.get(b, [])
        gens_here = df_gen_all[df_gen_all['BusNum'].isin(orig_nodes)]
        if gens_here.empty:
            continue
        fuels_here = gens_here['FuelType'].unique()
        if 'WND (Wind)' in fuels_here:
            has_wind[b] = True
        if 'SUN (Solar)' in fuels_here:
            has_solar[b] = True

    # ==========================
    # TRANSMISSION (NN, Tp)
    # ==========================
    for Tp_pct in trans_p:
        # Create Exp folder once per NN/UC/Tp/year/section later; but transmission matrices do not depend on year/section.
        # Compute and save once per NN/Tp.
        T_p = Tp_pct/100
        df_branch = pd.read_excel(os.path.join(base_dir, FN), sheet_name='Branch',header=0)


# =============================================================================
# 
#         # eliminate repeats
#         df = df_branch.copy()
#         lines = []
#         repeats = []
#         index = []
#         for i in range(0,len(df)):
#             t=tuple((df.loc[i,'fbus'],df.loc[i,'tbus']))
#             if t in lines:
#                 df = df.drop([i])
#                 repeats.append(t)
#                 r = lines.index(t)
#                 ii = index[r]
#                 df.loc[ii,'rateA'] += df.loc[ii,'rateA']
#             else:
#                 lines.append(t)
#                 index.append(i)
#         df = df.reset_index(drop=True)
# 
# 
# =============================================================================

        
        # ==========================================================
        # Remove duplicated transmission lines from Results_{NN}
        # Treat lines as undirected:
        #   fbus -> tbus and tbus -> fbus are considered the same line.
        # Retain the row with the larger capacity.
        #
        # Capacity priority:
        #   1) If rateA exists and is positive, use rateA.
        #   2) Otherwise, use implied DC capacity = 100 / x.
        # ==========================================================
        
        df = df_branch.copy()
        
        # Create an undirected line key: smaller bus first, larger bus second
        df['bus_min'] = df[['fbus', 'tbus']].min(axis=1)
        df['bus_max'] = df[['fbus', 'tbus']].max(axis=1)
        df['undirected_key'] = list(zip(df['bus_min'], df['bus_max']))
        
        # Define the capacity used to decide which duplicate to retain
        if 'rateA' in df.columns:
            df['capacity_for_filter'] = pd.to_numeric(df['rateA'], errors='coerce')
        else:
            df['capacity_for_filter'] = np.nan
        
        # If rateA is missing, zero, or invalid, fall back to 100 / x
        df['x_for_filter'] = pd.to_numeric(df['x'], errors='coerce')
        df['implied_capacity_for_filter'] = 100 / df['x_for_filter']
        
        df['capacity_for_filter'] = df['capacity_for_filter'].where(
            df['capacity_for_filter'].notna() & (df['capacity_for_filter'] > 0),
            df['implied_capacity_for_filter']
        )
        
        # Sort so the largest-capacity line appears first within each undirected pair
        df = df.sort_values(
            by=['undirected_key', 'capacity_for_filter'],
            ascending=[True, False]
        )
        
        # Keep only the largest-capacity line for each undirected pair
        df = df.drop_duplicates(subset='undirected_key', keep='first').reset_index(drop=True)
        
        # Optional: print how many duplicated undirected lines were removed
        n_removed = len(df_branch) - len(df)
        print(
            f"NN={NN}, Tp={Tp_pct}: removed {n_removed} duplicated undirected transmission lines "
            f"from Results_{NN}.xlsx Branch sheet."
        )
        
        # Clean temporary columns
        df = df.drop(
            columns=[
                'bus_min',
                'bus_max',
                'undirected_key',
                'capacity_for_filter',
                'x_for_filter',
                'implied_capacity_for_filter'
            ],
            errors='ignore'
        )


        sources = df.loc[:,'fbus']
        sinks = df.loc[:,'tbus']
        combined = np.append(sources, sinks)
        df_combined = pd.DataFrame(combined,columns=['node'])
        unique_nodes = df_combined['node'].unique()
        unique_nodes.sort()

        A = np.zeros((len(df),len(unique_nodes)))
        df_line_to_bus = pd.DataFrame(A)
        df_line_to_bus.columns = unique_nodes

        negative = []
        positive = []
        lines_lbl = []
        ref_node = 0
        reactance = []
        limit = []

        for i in range(0,len(df)):
            s = df.loc[i,'fbus']
            k = df.loc[i,'tbus']
            line = str(s) + '_' + str(k)
            if s == df.loc[0,'fbus']:
                lines_lbl.append(line)
                positive.append(s)
                negative.append(k)
                df_line_to_bus.loc[ref_node,s] = 1
                df_line_to_bus.loc[ref_node,k] = -1
                reactance.append(df.loc[i,'x'])
                MW = (1/df.loc[i,'x'])*100*(1+T_p)
                limit.append(MW)
                ref_node += 1
            elif k == df.loc[0,'fbus']:
                lines_lbl.append(line)
                positive.append(k)
                negative.append(s)
                df_line_to_bus.loc[ref_node,k] = 1
                df_line_to_bus.loc[ref_node,s] = -1
                reactance.append(df.loc[i,'x'])
                MW = (1/df.loc[i,'x'])*100*(1+T_p)
                limit.append(MW)
                ref_node += 1

        for i in range(0,len(df)):
            s = df.loc[i,'fbus']
            k = df.loc[i,'tbus']
            line = str(s) + '_' + str(k)
            if s != df.loc[0,'fbus'] and k != df.loc[0,'fbus']:
                lines_lbl.append(line)
                if s in positive and k in negative:
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                elif k in positive and s in negative:
                    df_line_to_bus.loc[ref_node,k] = 1
                    df_line_to_bus.loc[ref_node,s] = -1
                elif s in positive and k in positive:
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                elif s in negative and k in negative:
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                elif s in positive:
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                    negative.append(k)
                elif s in negative:
                    df_line_to_bus.loc[ref_node,k] = 1
                    df_line_to_bus.loc[ref_node,s] = -1
                    positive.append(k)
                elif k in positive:
                    df_line_to_bus.loc[ref_node,k] = 1
                    df_line_to_bus.loc[ref_node,s] = -1
                    negative.append(s)
                elif k in negative:
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                    positive.append(s)
                else:
                    positive.append(s)
                    negative.append(k)
                    df_line_to_bus.loc[ref_node,s] = 1
                    df_line_to_bus.loc[ref_node,k] = -1
                reactance.append(df.loc[i,'x'])
                MW = (1/df.loc[i,'x'])*100*(1+T_p)
                limit.append(MW)
                ref_node += 1

        unique_nodes = list(unique_nodes)
        unique_nodes_lbl = ['bus_' + str(v) for v in unique_nodes]
        df_line_to_bus.columns = unique_nodes_lbl
        for i in range(0,len(lines_lbl)):
            lines_lbl[i] = 'line_' + lines_lbl[i]
        df_line_to_bus['line'] = lines_lbl
        df_line_to_bus.set_index('line', inplace=True)
        
        # FIX: keep 'line' as an explicit first column in the CSV
        df_line_to_bus_out = df_line_to_bus.reset_index()  # 'line' becomes first column
        
        fn_line_to_bus = f'line_to_bus_{NN}_tp_{Tp_pct}.csv'
        full_line_to_bus_path = _save_csv(df_line_to_bus_out, fn_line_to_bus, index=False)

        df_line_params = pd.DataFrame()
        df_line_params['line'] = lines_lbl
        df_line_params['reactance'] = reactance
        df_line_params['limit'] = limit
        fn_line_params = f'line_params_{NN}_tp_{Tp_pct}.csv'
        full_line_params_path = _save_csv(df_line_params, fn_line_params, index=False)

        # ==========================
        # UC treatment loop (behavior unchanged)
        # ==========================
        for UC in UC_TREATMENTS:
            for y in years:
                # Pre-load annual BA profiles once per y
                y_string = str(y)
                fn_load = 'Load/BA_load_corrected_' + y_string + '.csv'
                df_load = pd.read_csv(os.path.join(base_dir, fn_load), header=0, index_col=0)
                fn_wind = 'Gen/BA_wind_corrected_' + y_string + '.csv'
                df_wind = pd.read_csv(os.path.join(base_dir, fn_wind), header=0,index_col=0)
                fn_solar = 'Gen/BA_solar_corrected_' + y_string + '.csv'
                df_solar = pd.read_csv(os.path.join(base_dir, fn_solar), header=0,index_col=0)

                # clean NaNs for generators (same as before)
                for _df in (df_wind, df_solar, df_hydro):
                    a = _df.values
                    m=np.where(np.isnan(a))
                    r,c=np.shape(m)
                    for i in range(0,c):
                        _df.iloc[m[0][i],m[1][i]] = 0

                # Keep legacy Exp folder behavior
                path=str(Path.cwd()) + str(Path('/Exp' + str(NN) + UC + '_' + str(Tp_pct) + '_' + str(y)))
                os.makedirs(path,exist_ok=True)

                # -----------------
                # NODAL LOAD (NN, year)
                # -----------------
                T = np.zeros((8760,len(buses)))
                for i in range(0,len(df_selected)):
                    name = df_selected.loc[i,'BA']
                    if float(df_BA_totals_load.loc[df_BA_totals_load['Name']==str(name),'Total'].values[0]) < 1:
                        pass
                    else:
                        abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                        weight = df_selected.loc[i,'BA Load Weight']
                        if max(df_load[abbr]) < 1:
                            T[:,i] += np.reshape(df_load[abbr].values,(8760,))
                        else:
                            T[:,i] += np.reshape(df_load[abbr].values*weight,(8760,))
                buses_lbl = ['bus_' + str(b) for b in buses]
                df_C = pd.DataFrame(T, columns=buses_lbl)
                fn_load_out = f'nodal_load_{NN}_y_{y}.csv'
                full_load_path = _save_csv(df_C, fn_load_out)
                #copy(full_load_path, path)

                # ============= WIND (per year) =============
                df_gen = pd.read_csv(os.path.join(base_dir, 'Gen/Generators_EIA.csv'), header=0)
                MWMax = []
                fuel_type = []
                nums = list(df_gen['BusNum'])
                for i in range(0,len(df_full)):
                    bus = df_full.loc[i,'Number']
                    if bus in nums:
                        MWMax.append(df_gen.loc[df_gen['BusNum']==bus,'MWMax'].values[0])
                        fuel_type.append(df_gen.loc[df_gen['BusNum']==bus,'FuelType'].values[0])
                    else:
                        MWMax.append(0)
                        fuel_type.append('none')
                df_full['MWMax'] = MWMax
                df_full['FuelType'] = fuel_type

                BA_totals = []
                for b in BAs:
                    sample = list(df_full.loc[(df_full['NAME']==b) & (df_full['FuelType'] == 'WND (Wind)'),'MWMax'])
                    BA_totals.append(sum(sample))
                df_BA_totals = pd.DataFrame(np.column_stack((BAs,BA_totals)), columns=['Name','Total'])

                weights = []
                for i in range(0,len(df_full)):
                    area = df_full.loc[i,'NAME']
                    if str(area) in BAs and str(df_full.loc[i,'FuelType']) == 'WND (Wind)':
                        X = float(df_BA_totals.loc[df_BA_totals['Name']==area,'Total'].iloc[0])
                        W = df_full.loc[i,'MWMax']/X
                        weights.append(W)
                    else:
                        weights.append(0)
                df_full['BA Wind Weight'] = weights

                buses = list(df_selected['bus_i'])
                T = np.zeros((8760,len(buses)))
                BA_sums = np.zeros((len(BAs),1))
                BA_test = np.zeros((len(BAs),1))

                idx = 0
                for b in buses:
                    sample = df_full.loc[df_full['Number'] == b].reset_index(drop=True)
                    name = sample['NAME'][0]
                    if str(name) in BAs and float(df_BA_totals.loc[df_BA_totals['Name']==str(name),'Total'].values[0]) >= 1:
                        abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                        weight = sample['BA Wind Weight'].values[0]
                        T[:,idx] += np.reshape(df_wind[abbr].values*weight,(8760,))
                        dx = BAs.index(name)
                        BA_sums[dx] += weight
                        BA_test[dx] += sum(df_wind[abbr].values*weight)
                    try:
                        m_nodes = merged[b]
                        for m in m_nodes:
                            sample = df_full.loc[df_full['Number'] == m].reset_index(drop=True)
                            name = sample['NAME'][0]
                            if str(name) in BAs and float(df_BA_totals.loc[df_BA_totals['Name']==str(name),'Total'].values[0]) >= 1:
                                abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                                weight = sample['BA Wind Weight']
                                dx = BAs.index(name)
                                BA_sums[dx] += weight
                                BA_test[dx] += sum(df_wind[abbr].values*weight.values[0])
                                T[:,idx] += np.reshape(df_wind[abbr].values*weight.values[0],(8760,))
                    except KeyError:
                        pass
                    idx += 1
                w_buses = ['bus_' + str(b) for b in buses]
                df_C = pd.DataFrame(T, columns=w_buses)
                fn_wind_out = f'nodal_wind_{NN}_y_{y}.csv'
                full_wind_path = _save_csv(df_C, fn_wind_out)
                #copy(full_wind_path, path)

                # ============= SOLAR (per year) =============
                BA_totals = []
                for b in BAs:
                    sample = list(df_full.loc[(df_full['NAME']==b) & (df_full['FuelType'] == 'SUN (Solar)'),'MWMax'])
                    BA_totals.append(sum(sample))
                df_BA_totals = pd.DataFrame(np.column_stack((BAs,BA_totals)), columns=['Name','Total'])

                weights = []
                for i in range(0,len(df_full)):
                    area = df_full.loc[i,'NAME']
                    if str(area) in BAs and str(df_full.loc[i,'FuelType']) == 'SUN (Solar)':
                        X = float(df_BA_totals.loc[df_BA_totals['Name']==area,'Total'].iloc[0])
                        W = df_full.loc[i,'MWMax']/X
                        weights.append(W)
                    else:
                        weights.append(0)
                df_full['BA Solar Weight'] = weights

                T = np.zeros((8760,len(buses)))
                BA_sums = np.zeros((len(BAs),1))

                idx = 0
                for b in buses:
                    sample = df_full.loc[df_full['Number'] == b].reset_index(drop=True)
                    name = sample['NAME'][0]
                    if str(name) in BAs and float(df_BA_totals.loc[df_BA_totals['Name']==str(name),'Total'].values[0]) >= 1:
                        abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                        weight = sample['BA Solar Weight'].values[0]
                        T[:,idx] += np.reshape(df_solar[abbr].values*weight,(8760,))
                        dx = BAs.index(name)
                        BA_sums[dx] += weight
                    try:
                        m_nodes = merged[b]
                        for m in m_nodes:
                            sample = df_full.loc[df_full['Number'] == m].reset_index(drop=True)
                            name = sample['NAME'][0]
                            if str(name) in BAs and float(df_BA_totals.loc[df_BA_totals['Name']==str(name),'Total'].values[0]) >= 1:
                                abbr = df_BAs.loc[df_BAs['Name']==name,'Abbreviation'].values[0]
                                weight = sample['BA Solar Weight']
                                dx = BAs.index(name)
                                BA_sums[dx] += weight
                                T[:,idx] += np.reshape(df_solar[abbr].values*weight.values[0],(8760,))
                    except KeyError:
                        pass
                    idx += 1
                s_buses = ['bus_' + str(b) for b in buses]
                df_C = pd.DataFrame(T, columns=s_buses)
                fn_solar_out = f'nodal_solar_{NN}_y_{y}.csv'
                full_solar_path = _save_csv(df_C, fn_solar_out)
                #copy(full_solar_path, path)
            #########################################
            # GENERATOR PARAMS (full + aggregated oil)
                # Note: these remain written per NN (filename), same as v1; behavior preserved (overwrites across years).
                df_G = pd.read_csv(full_thermal_path,header=0)

                names = []
                typs = []
                nodes = []
                maxcaps = []
                mincaps = []
                heat_rates = []
                var_oms = []
                no_loads = []
                st_costs = []
                ramps = []
                minups = []
                mindns = []

                must_nodes = []
                must_caps = []

                for i in range(0,len(df_G)):
                    name = df_G.loc[i,'Name']
                    t = df_G.loc[i,'Fuel']
                    if t == 'NG (Natural Gas)':
                        typ = 'ngcc'
                    elif t == 'BIT (Bituminous Coal)':
                        typ = 'coal'
                    elif t == 'DFO (Distillate Fuel Oil)':
                        typ = 'oil'
                    else:
                        typ = 'nuclear'
                    node = 'bus_' + str(df_G.loc[i,'Bus'])
                    maxcap = df_G.loc[i,'Max_Cap']
                    mincap = df_G.loc[i,'Min_Cap']
                    hr_2 = df_G.loc[i,'Heat_Rate']

                    if typ == 'ngcc':
                        var_om = 3; minup = 4; mindn = 4; ramp = maxcap
                    elif typ == 'oil':
                        var_om = 8; minup = 1; mindn = 1; ramp = maxcap
                    else:
                        var_om = 4; minup = 12; mindn = 12; ramp = 0.33*maxcap
                    st_cost = 70*maxcap; no_load = 3*maxcap

                    if typ != 'nuclear':
                        names.append(name); typs.append(typ); nodes.append(node)
                        maxcaps.append(maxcap); mincaps.append(mincap)
                        var_oms.append(var_om); no_loads.append(no_load); st_costs.append(st_cost)
                        ramps.append(ramp); minups.append(minup); mindns.append(mindn); heat_rates.append(hr_2)
                    else:
                        must_nodes.append(node); must_caps.append(maxcap)

                # wind
                df_W = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_wind_{NN}_y_{y}.csv'), header=0)
                for b in buses_reduced:
                    node_lbl = f'bus_{b}'
                    # We still require the column to exist in df_W, but presence is decided by has_wind
                    if node_lbl in df_W.columns and has_wind.get(b, False):
                        name = node_lbl + '_WIND'
                        maxcap = 100000
                        names.append(name); typs.append('wind'); nodes.append(node_lbl)
                        maxcaps.append(maxcap); mincaps.append(0)
                        var_oms.append(0); no_loads.append(0); st_costs.append(0)
                        ramps.append(0); minups.append(0); mindns.append(0); heat_rates.append(0)

                # solar
                df_S = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_solar_{NN}_y_{y}.csv'), header=0)
                for b in buses_reduced:
                    node_lbl = f'bus_{b}'
                    if node_lbl in df_S.columns and has_solar.get(b, False):
                        name = node_lbl + '_SOLAR'
                        maxcap = 100000
                        names.append(name); typs.append('solar'); nodes.append(node_lbl)
                        maxcaps.append(maxcap); mincaps.append(0)
                        var_oms.append(0); no_loads.append(0); st_costs.append(0)
                        ramps.append(0); minups.append(0); mindns.append(0); heat_rates.append(0)

                # hydro
                df_H = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_hydro_{NN}.csv'),header=0)
                for ncol in df_H.columns:
                    if sum(df_H[ncol]) > 0:
                        name = ncol + '_HYDRO'; maxcap = max(df_H[ncol])
                        names.append(name); typs.append('hydro'); nodes.append(ncol)
                        maxcaps.append(maxcap); mincaps.append(0)
                        var_oms.append(1); no_loads.append(1); st_costs.append(1)
                        ramps.append(maxcap); minups.append(0); mindns.append(0); heat_rates.append(0)

                df_genparams = pd.DataFrame()
                df_genparams['name'] = names
                df_genparams['typ'] = typs
                df_genparams['node'] = nodes
                df_genparams['maxcap'] = maxcaps
                df_genparams['heat_rate'] = heat_rates
                df_genparams['mincap'] = mincaps
                df_genparams['var_om'] = var_oms
                df_genparams['no_load'] = no_loads
                df_genparams['st_cost'] = st_costs
                df_genparams['ramp'] = ramps
                df_genparams['minup'] = minups
                df_genparams['mindn'] = mindns

                fn_genparams_full = f'data_genparams_full_{NN}.csv'
                full_genparams_full_path = _save_csv(df_genparams, fn_genparams_full, index=False)
                #copy(full_genparams_full_path, path)

                df_must = pd.DataFrame()
                for i in range(0,len(must_nodes)):
                    ncol = must_nodes[i]
                    df_must[ncol] = [must_caps[i]]
                fn_must = f'must_run_{NN}.csv'
                full_must_path = _save_csv(df_must, fn_must, index=False)
                #copy(full_must_path, path)

                # Gen-to-bus matrix (full)
                df = pd.read_csv(full_genparams_full_path,header=0)
                gens = list(df.loc[:,'name'])
                df_nodes = pd.read_excel(os.path.join(base_dir, FN), sheet_name = 'Bus', header=0)
                all_nodes = list(df_nodes['bus_i'])
                all_nodes = ['bus_' + str(v) for v in all_nodes]
                A = np.zeros((len(gens),len(all_nodes)))
                df_A = pd.DataFrame(A, columns=all_nodes)
                df_A['name'] = gens
                df_A.set_index('name',inplace=True)
                for i in range(0,len(gens)):
                    node = df.loc[i,'node']
                    g = gens[i]
                    df_A.loc[g,node] = 1
                fn_gen_mat_full = f'gen_mat_full_{NN}.csv'
                full_gen_mat_full_path = _save_csv(df_A, fn_gen_mat_full, index=True)
                #copy(full_gen_mat_full_path, path)

                # Aggregate oil on nodes and rewrite params (same logic)
                df = pd.read_csv(full_genparams_full_path,header=0)
                df_oil = df.loc[df['typ'] == 'oil'].reset_index(drop=True)
                gens = list(df.loc[:,'name'])
                gens_oil = list(df_oil.loc[:,'name'])
                gens_cap = list(df.loc[:,'maxcap'])
                gens_hr = list(df.loc[:,'heat_rate'])
                gens_min = list(df.loc[:,'mincap'])
                gens_var_om = list(df.loc[:,'var_om'])
                gens_no_load = list(df.loc[:,'no_load'])
                gens_st_cost = list(df.loc[:,'st_cost'])
                gens_ramp = list(df.loc[:,'ramp'])

                df_nodes = pd.read_excel(os.path.join(base_dir, FN), sheet_name = 'Bus', header=0)
                all_nodes = list(df_nodes['bus_i'])
                df_gen_mat = pd.read_csv(full_gen_mat_full_path,header=0)

                all_nodes_lbl = ['bus_' + str(v) for v in all_nodes]
                df_nodes['bus_i'] = all_nodes_lbl
                A = np.zeros((len(gens),len(all_nodes_lbl)))
                df_A = pd.DataFrame(A, columns=all_nodes_lbl)
                df_A['name'] = gens
                df_A.set_index('name',inplace=True)
                for i in range(0,len(gens_oil)):
                    node = df_oil.loc[i,'node']
                    g = gens_oil[i]
                    df_A.loc[g,node] = 1

                tot_cap = np.zeros(len(all_nodes_lbl))
                oil_cap = np.zeros(len(all_nodes_lbl))
                oil_max = np.zeros(len(all_nodes_lbl))
                oil_hr = np.zeros(len(all_nodes_lbl))
                oil_min = np.zeros(len(all_nodes_lbl))
                oil_var_om = np.zeros(len(all_nodes_lbl))
                oil_no_load = np.zeros(len(all_nodes_lbl))
                oil_st_cost = np.zeros(len(all_nodes_lbl))
                oil_ramp = np.zeros(len(all_nodes_lbl))

                for i in range(0,len(all_nodes_lbl)):
                    tot_cap[i] = sum(gens_cap*df_gen_mat.iloc[:,i+1])
                    oil_cap[i] = sum(gens_cap*df_A.iloc[:,i])
                    oil_max[i] = sum(gens_cap*df_A.iloc[:,i])
                    oil_hr[i] = sum(gens_hr*(gens_cap*df_A.iloc[:,i])/sum(gens_cap*df_A.iloc[:,i]))
                    oil_min[i] = sum(gens_min*(gens_cap*df_A.iloc[:,i])/sum(gens_cap*df_A.iloc[:,i]))
                    oil_var_om[i] = sum(gens_var_om*(gens_cap*df_A.iloc[:,i])/sum(gens_cap*df_A.iloc[:,i]))
                    oil_no_load[i] = sum(gens_no_load*(gens_cap*df_A.iloc[:,i])/sum(gens_cap*df_A.iloc[:,i]))
                    oil_st_cost[i] = sum(gens_st_cost*(gens_cap*df_A.iloc[:,i])/sum(gens_cap*df_A.iloc[:,i]))
                    oil_ramp[i] = sum(gens_ramp*df_A.iloc[:,i])

                df_oil = pd.DataFrame()
                df_oil.loc[:,'node'] = list(df_nodes.loc[:,'bus_i'])
                df_oil.loc[:,'maxcap'] = oil_max
                df_oil.loc[:,'heat_rate'] = oil_hr
                df_oil.loc[:,'mincap'] = oil_min
                df_oil.loc[:,'var_om'] = oil_var_om
                df_oil.loc[:,'no_load'] = oil_no_load
                df_oil.loc[:,'st_cost'] = oil_st_cost
                df_oil.loc[:,'ramp'] = oil_ramp
                df_oil = df_oil.dropna().reset_index(drop=True)

                # If aggregation produced no valid rows (e.g., no oil gens anywhere), skip gracefully
                if df_oil.empty:
                    df = df.loc[df['typ'] != 'oil']
                else:
                    df_oil = df_oil.copy()
                    df_oil['minup'] = 1
                    df_oil['mindn'] = 1
                    df_oil['typ'] = 'oil'
                    oil_name = []
                    for i in range(0,len(df_oil.index)):
                        oil_name.append(df_oil.loc[i,'node'] + '_oil')
                    df_oil['name'] = oil_name
                    df_oil = df_oil[["name", "typ", "node", "maxcap", "heat_rate", "mincap", "var_om", "no_load", "st_cost", "ramp", "minup", "mindn"]]
                    df = df.loc[df['typ'] != 'oil']
                    df = pd.concat([df, df_oil], ignore_index=True)
                fn_genparams = f'data_genparams_{NN}.csv'
                full_genparams_path = _save_csv(df, fn_genparams, index=False)
                #copy(full_genparams_path, path)

                # Recreate gen-to-bus matrix
                df = pd.read_csv(full_genparams_path,header=0)
                gens = list(df.loc[:,'name'])
                df_nodes = pd.read_excel(os.path.join(base_dir, FN), sheet_name = 'Bus', header=0)
                all_nodes = ['bus_' + str(v) for v in list(df_nodes['bus_i'])]
                A = np.zeros((len(gens),len(all_nodes)))
                df_A = pd.DataFrame(A, columns=all_nodes)
                df_A['name'] = gens
                df_A.set_index('name',inplace=True)
                for i in range(0,len(gens)):
                    node = df.loc[i,'node']
                    g = gens[i]
                    df_A.loc[g,node] = 1
                fn_gen_mat = f'gen_mat_{NN}.csv'
                full_gen_mat_path = _save_csv(df_A, fn_gen_mat, index=True)
                #copy(full_gen_mat_path, path)


                # -----------------
                # YEAR-SPECIFIC FUEL PRICES
                # -----------------

                # Natural gas price by BA
                NG_price = pd.read_csv(
                    os.path.join(base_dir, f'NG_price/Average_NG_prices_BAs_{y_string}.csv'),
                    header=0
                )

                Fuel_buses = ['bus_' + str(b) for b in buses]

                NG_prices_all = None
                for bus in buses:
                    selected_node_BA = df_full.loc[df_full['Number'] == bus, 'NAME'].values[0]
                    specific_node_NG_price = NG_price.loc[:, selected_node_BA].copy()

                    NG_prices_all = (
                        specific_node_NG_price.copy()
                        if NG_prices_all is None
                        else pd.concat([NG_prices_all, specific_node_NG_price], axis=1)
                    )

                if NG_prices_all is None:
                    NG_prices_all = pd.DataFrame(columns=Fuel_buses)

                NG_prices_all.columns = Fuel_buses


                # Coal price by state
                Coal_price = pd.read_csv(
                    os.path.join(base_dir, f'Coal_price/coal_prices_state_{y_string}.csv'),
                    header=0
                )

                Coal_prices_all = None
                for bus in buses:
                    selected_node_state = df_full.loc[df_full['Number'] == bus, 'STATE'].values[0]

                    # Existing state substitutions
                    if selected_node_state == 'NB':
                        selected_node_state = 'ME'
                    elif selected_node_state == 'CO':
                        selected_node_state = 'KS'
                    elif selected_node_state == 'OR':
                        selected_node_state = 'AR'
                    elif selected_node_state == 'TX':
                        selected_node_state = 'OK'
                    elif selected_node_state == 'NM':
                        selected_node_state = 'OK'
                    elif selected_node_state == 'MT':
                        selected_node_state = 'SD'

                    specific_node_coal_price = Coal_price.loc[:, selected_node_state].copy()

                    Coal_prices_all = (
                        specific_node_coal_price.copy()
                        if Coal_prices_all is None
                        else pd.concat([Coal_prices_all, specific_node_coal_price], axis=1)
                    )

                if Coal_prices_all is None:
                    Coal_prices_all = pd.DataFrame(columns=Fuel_buses)

                Coal_prices_all.columns = Fuel_buses


                # Oil still fixed unless you also want oil to vary by year
                Oil_prices_all = pd.DataFrame({
                    'all': np.reshape(np.ones((365, 1)) * 20, (365,))
                })


                # ============= Fuel price mapping to gens (NN-only structures, but gen list is year-specific)
                thermal_gens_info = df.loc[(df['typ']=='ngcc') | (df['typ']=='coal') | (df['typ']=='oil')].copy()
                thermal_gens_names = [*thermal_gens_info['name']]
                Fuel_prices_all = None
                for _, row in thermal_gens_info.iterrows():
                    if row['typ'] == 'ngcc':
                        gen_fuel_price = NG_prices_all.loc[:, row['node']].copy()
                    elif row['typ'] == 'coal':
                        gen_fuel_price = Coal_prices_all.loc[:, row['node']].copy()
                    elif row['typ'] == 'oil':
                        gen_fuel_price = Oil_prices_all.loc[:,'all'].copy()
                    Fuel_prices_all = gen_fuel_price.copy() if Fuel_prices_all is None else pd.concat([Fuel_prices_all, gen_fuel_price], axis=1)
                if Fuel_prices_all is None:
                    Fuel_prices_all = pd.DataFrame()
                Fuel_prices_all.columns = thermal_gens_names
                
                #fn_fuel_prices = f'Fuel_prices_{NN}.csv'
                #full_fuel_prices_path = _save_csv(Fuel_prices_all, fn_fuel_prices, index=False)
                #copy(full_fuel_prices_path, path)

                fn_fuel_prices = f'Fuel_prices_{NN}_y_{y}.csv'
                full_fuel_prices_path = _save_csv(Fuel_prices_all, fn_fuel_prices, index=False)

                # copy other driver files (unchanged behavior)
                w = 'wrapper' + UC + '.py'
                milp = 'EIC_MILP' + UC + '.py'
                lp = 'EIC_LP' + UC + '.py'
                copy(w,path)
                #copy('EICDataSetup.py',path)
                if UC == '_simple':
                    copy('EIC' + UC + '.py',path)
                else:
                    copy(milp,path)
                    copy(lp,path)

                # Generator outages & loss dict
                loss_src = _lostcap_src_for_year(base_dir, y_string)
                
                # Save to a standardized year-specific name in Data/data_allocation
                loss_dst = os.path.join(data_allocation_dir, f'east{y_string}_lostcap_v4.csv')
                copy(loss_src, loss_dst)
                
                print(f"Copied lost-cap file for year {y_string}: {loss_src} -> {loss_dst}")
                
                from dict_creator import dict_funct
                df_loss_dict = dict_funct(df)
                
                npy_path = os.path.join(data_allocation_dir, f'df_dict2_{NN}.npy')
                np.save(npy_path, df_loss_dict)
                #copy(npy_path, path)
