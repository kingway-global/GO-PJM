# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
from geopy import distance
# import descartes
import geopandas as gpd
from shapely.geometry import Point, Polygon
from matplotlib.colors import TwoSlopeNorm

base_dir = 'Data'

RTS = [500]
#RTS = [500, 525, 550, 575, 600, 625, 650, 675, 700]
distance_threshold = 5

df_BAs = pd.read_csv(os.path.join(base_dir, 'Interconnections/BAs_full.csv'), header=0, index_col=0)

# Reference table maps BA polygon names (geometry layer) to standard EIA abbreviations.
BAs_ref = pd.read_excel(os.path.join(base_dir, 'Interconnections/BAs_reference_table.xlsx'), header=0)

# Map BA names (either geometry NAME or EIA-standard NAME) -> EIA BA abbreviations (upper-case)
abbr_mapping = {}
for _, _r in BAs_ref.iterrows():
    abbr = str(_r.get('Abbreviation_EIA', '')).strip().upper()
    if not abbr or abbr.lower() == 'nan':
        continue
    # allow mapping from both geometry-layer names and EIA-standard names
    for _kcol in ['Name_geometry', 'Name_EIA']:
        if _kcol not in BAs_ref.columns:
            continue
        k = _r.get(_kcol, None)
        if k is None or (isinstance(k, float) and pd.isna(k)):
            continue
        k = str(k).strip()
        if not k or k.lower() == 'nan':
            continue
        abbr_mapping[k] = abbr

# Optional: mapping from geometry NAME -> EIA-standard NAME (to overwrite joined['NAME'] like original mapper)
name_mapping = dict(zip(BAs_ref['Name_geometry'], BAs_ref['Name_EIA'])) if 'Name_EIA' in BAs_ref.columns else {}

# Keep original BA polygon NAMEs (do NOT standardize NAME in outputs).
# We use this list only to filter to the study BA set when building nodes_to_BA_state*.csv.
if 'Name' in df_BAs.columns:
    _bas_full = df_BAs['Name'].dropna().astype(str).tolist()
else:
    # Fallback: use the first column if schema differs
    _bas_full = df_BAs.iloc[:, 0].dropna().astype(str).tolist()
_bas_ref = []
if 'Name_geometry' in BAs_ref.columns:
    _bas_ref += BAs_ref['Name_geometry'].dropna().astype(str).tolist()
if 'Name_EIA' in BAs_ref.columns:
    _bas_ref += BAs_ref['Name_EIA'].dropna().astype(str).tolist()
BAs = sorted(set([x.strip() for x in (_bas_full + _bas_ref) if str(x).strip().lower() != 'nan' and str(x).strip() != '']))

df = pd.read_csv(os.path.join(base_dir, 'Interconnections/EIC.csv'), header=0)
crs = {'init':'epsg:4326'}
# crs = {"init": "epsg:2163"}
geometry = [Point(xy) for xy in zip(df['Substation Longitude'],df['Substation Latitude'])]
filter_nodes = gpd.GeoDataFrame(df,crs=crs,geometry=geometry)
nodes_df = gpd.GeoDataFrame(df,crs=crs,geometry=geometry)
nodes_df = nodes_df.to_crs(epsg=2163)

BAs_gdf = gpd.read_file(os.path.join(base_dir, 'reduced_network/Control_Areas.shp'))
BAs_gdf = BAs_gdf.to_crs(epsg=2163)

states_gdf = gpd.read_file(os.path.join(base_dir, 'reduced_network/geo_export_9ef76f60-e019-451c-be6b-5a879a5e7c07.shp'))
states_gdf = states_gdf.to_crs(epsg=2163)

# Spatially join buses to BA polygons and states
try:
    joined = gpd.sjoin(nodes_df, BAs_gdf, how='left', predicate='within')
    joined2 = gpd.sjoin(nodes_df, states_gdf, how='left', predicate='within')
except TypeError:
    # geopandas<0.10 compatibility
    joined = gpd.sjoin(nodes_df, BAs_gdf, how='left', op='within')
    joined2 = gpd.sjoin(nodes_df, states_gdf, how='left', op='within')

joined['State'] = joined2['state_name']
joined = joined.reset_index(drop=True)

# --- overwrite NAME to match EIA naming (like original mapper) ---
if isinstance(name_mapping, dict) and len(name_mapping) > 0 and 'NAME' in joined.columns:
    joined['NAME'] = joined['NAME'].replace(name_mapping)

# Normalize BA names to standard EIA abbreviations
joined['BA_ABBR'] = joined['NAME'].map(abbr_mapping)

# Fallback: if NAME already looks like an abbreviation (2-6 letters), use it
_mask = joined['BA_ABBR'].isna()
_cand = joined.loc[_mask, 'NAME'].astype(str).str.strip()
_cand = _cand.where(_cand.str.fullmatch(r'[A-Za-z]{2,6}'))
joined.loc[_mask, 'BA_ABBR'] = _cand

joined['BA_ABBR'] = joined['BA_ABBR'].astype(str).str.upper()
joined.loc[joined['BA_ABBR'].isin(['NAN', 'NONE', '']), 'BA_ABBR'] = np.nan

# Use abbreviation as canonical BA identifier everywhere below
# NOTE: do NOT overwrite joined['NAME']; keep original shapefile NAME for downstream consistency.

buses = list(joined['Number'])
B = []
for b in buses:
    if b in B:
        pass
    else:
        B.append(b)
    
#elimate redundant buses (overlapping BAs) based on peak load and 
#location within BAs

selected_BAs = []
end_nodes = []

for b in B:

    sample = joined[joined['Number'] == b]
    index_list = list(sample.index)
    sample = sample.reset_index(drop=True)

    TELL_ok = []

    if len(sample) > 1:
    
        for i in range(0,len(sample)):
            if sample.loc[i,'NAME'] in BAs:
                TELL_ok.append(i)
    
        if len(TELL_ok)<1:
        
            smallest = min(sample['SHAPE_Area'])
            selection = sample[sample['SHAPE_Area']==smallest]
        
        else:
        
            t = 0
            m = 100000000000000000000
            for i in range(0,len(TELL_ok)):
                if sample.loc[TELL_ok[i],'NAME'] in selected_BAs:
                    if sample.loc[TELL_ok[i],'SHAPE_Area'] < m:
                        m = sample.loc[TELL_ok[i],'SHAPE_Area']
                else:
                    t = 1
                    selection = sample.loc[TELL_ok[i],:]
                    end_nodes.append(selection.name+index_list[0])
                    selected_BAs.append(sample.loc[TELL_ok[i],'NAME'])
                    break 
                
            if t < 1:
                selection = sample.loc[sample['SHAPE_Area']==m]
                end_nodes.append(selection.index.values[0]+index_list[0])
        
        
    else:
    
        selection = sample
    
        if sample['NAME'][0] in selected_BAs:
            pass
        else:
            selected_BAs.append(sample['NAME'][0])
            
        end_nodes.append(selection.index[0]+index_list[0])
    
    b_idx = B.index(b)
    print(b_idx)
    
    # end_nodes.append(selection['Number'].values[0])

    # if b_idx < 1:
    
    #     combined = selection
    #     end_nodes.append(selection['Number'])
        

    # else:
    
    #     combined = combined.append(selection) 
    
combined = joined.iloc[end_nodes,:]

combined_out = combined.drop(columns=['BA_ABBR'], errors='ignore')
combined_out.to_csv(os.path.join(base_dir, 'Interconnections/nodes_to_BA_state_original.csv'))

###########################################
# Remove any entry that is not in BA list
combined = combined.reset_index(drop=True)
count = 0
non_tell_BAs = []

for i in range(0,len(combined)):
   # print(i)
    a = combined.loc[i,'NAME']
    if a in BAs:
        pass
    else:
        if a in non_tell_BAs:
            pass
        else:
            non_tell_BAs.append(a)
        combined = combined.drop([i])
        count+=1

combined = combined.reset_index(drop=True)    
combined_out = combined.drop(columns=['BA_ABBR'], errors='ignore')
combined_out.to_csv(os.path.join(base_dir, 'Interconnections/nodes_to_BA_state.csv'))

##############################
#  Generators
##############################

import re
from itertools import compress

df_BA_states = pd.read_csv((os.path.join(base_dir, 'Interconnections/nodes_to_BA_state.csv')),index_col=0)

# Build an in-memory BA abbreviation column for grouping/splitting (do NOT write back to nodes_to_BA_state.csv).
df_BA_states['BA_ABBR'] = df_BA_states['NAME'].map(abbr_mapping)
_mask = df_BA_states['BA_ABBR'].isna()
_cand = df_BA_states.loc[_mask, 'NAME'].astype(str).str.strip()
_cand = _cand.where(_cand.str.fullmatch(r'[A-Za-z]{2,6}'))
df_BA_states.loc[_mask, 'BA_ABBR'] = _cand
df_BA_states['BA_ABBR'] = df_BA_states['BA_ABBR'].astype(str).str.upper()
df_BA_states.loc[df_BA_states['BA_ABBR'].isin(['NAN', 'NONE', '']), 'BA_ABBR'] = np.nan
df_BA_states.loc[df_BA_states['BA_ABBR'].isna() & df_BA_states['NAME'].astype(str).str.contains('PJM', case=False, na=False), 'BA_ABBR'] = 'PJM'

df_gens = pd.read_csv(os.path.join(base_dir, 'Gen/Generators_EIA.csv'))


###########################################
# Remove any entry that is not in BA list
nodes = list(df_BA_states['Number'])

for i in range(0,len(df_gens)):
    a = df_gens.loc[i,'BusNum']
    if a in nodes:
        pass
    else:
        df_gens = df_gens.drop([i])
df_gens = df_gens.reset_index(drop=True)

names = list(df_gens['BusName'])
BAs = []
c = list(df_BA_states.columns)
nx = int(c.index('NAME'))

# remove numbers and spaces
for n in names:
    i = names.index(n)
    corrected = re.sub(r'[^A-Z]',r'',n)
    names[i] = corrected
    BA = df_BA_states[df_BA_states['Number'] == df_gens.loc[i,'BusNum']]
    BAs.append(BA.iloc[0,nx])
    
df_gens['BusName'] = names
df_gens['BA'] = BAs
types = list(df_gens['FuelType'])

#select a single bus for each plant/BA combination (generators with the same name)

leftover = []
reduced_gen_buses = []
unique_bus_names = []
unique_bus_types = []
caps = []

for n in names:
    idx = names.index(n)
    if n in unique_bus_names:
        pass
    else:
        unique_bus_names.append(n)
        unique_bus_types.append(types[idx])
        
df_T = pd.DataFrame(unique_bus_types)
df_T.columns = ['Type']
df_T.to_csv(os.path.join(base_dir, 'reduced_network/reduced_types.csv.csv'))

for n in unique_bus_names:
    sample_ba = list(df_gens.loc[df_gens['BusName'] == n,'BA'].values)
    sample_bus_number = list(df_gens.loc[df_gens['BusName'] == n,'BusNum'].values)
    sample_bus_cap = list(df_gens.loc[df_gens['BusName'] == n,'MWMax'].values)
    
    s = []
    s_n = []
    s_c = []
    
    # record each BA for this plant
    for i in sample_ba:
        if i in s:
            pass
        else:
            s.append(i)
            
            #find max cap generator at this plant/BA combination
            idx = [ True if x == i else False for x in sample_ba]
            s_bn = list(compress(sample_bus_number,idx))
            s_cp = list(compress(sample_bus_cap,idx))
            mx = np.max(s_cp)
            total = np.sum(s_cp)
            idx2 = s_cp.index(mx)
            s_n.append(s_bn[idx2])
            s_c.append(total)
            
    if len(s)>1:
        if n in leftover:
            pass
        else:
            leftover.append(n)
        for j in range(0,len(s)):
            reduced_gen_buses.append(s_n[j])
            caps.append(s_c[j])
    else:
        reduced_gen_buses.append(s_n[0])
        caps.append(s_c[0])


##################################
#LOAD
##################################

df_load = pd.read_csv(os.path.join(base_dir, 'Interconnections/Buses_EIA.csv'))

for i in range(0,len(df_load)):
    a = df_load.loc[i,'Number']
    if a in nodes:
        pass
    else:
        df_load = df_load.drop([i])
df_load = df_load.reset_index(drop=True)

#pull all nodes with >0 load
non_zero = list(df_load.loc[df_load['Load MW']>0,'Number'])
unique_non_zero = []
for i in non_zero:
    if i in reduced_gen_buses:
        pass
    else:
        unique_non_zero.append(i)

#pull all nodes with voltage > 500kV
major_V = list(df_load.loc[df_load['Nom kV']>500,'Number'])
unique_major_V = []
for i in major_V:
    if i in reduced_gen_buses:
        pass
    elif i in unique_non_zero:
        pass
    else:
        unique_major_V.append(i)
        
#Calculate load weights for State/BA combinations
states = list(df_BA_states['State'].unique())
states = [x for x in states if str(x) != 'nan']
BAs = list(df_BA_states['NAME'].unique())
BAs = [x for x in BAs if str(x) != 'nan']

keys=[]
loads=[]
max_loads = []
max_load_vals = []

for i in non_zero:
    
    area = df_BA_states.loc[df_BA_states['Number']==i,'NAME'].values[0]
    state = df_BA_states.loc[df_BA_states['Number']==i,'State'].values[0]
    
    if str(area) == 'nan' or str(state) == 'nan':
        pass
    else:
    
        l = float(df_load.loc[df_load['Number'] == i, 'Load MW'].values[0])
        
        t = tuple([str(area),str(state)])
        
        if t in keys:
            idx=keys.index(t)
            loads[idx] += l
            if max_load_vals[idx] < l:
                max_load_vals[idx] = l
                max_loads[idx] = i
        else:
            keys.append(t)
            loads.append(l)
            max_loads.append(i)
            max_load_vals.append(l)

load_weights = np.array(loads, dtype=float) / np.sum(loads) if np.sum(loads) > 0 else np.array([])

#Create analogous generation weights

gens = []
gen_keys = []

for i in reduced_gen_buses:
    
    x = reduced_gen_buses.index(i)
    
    area = df_BA_states.loc[df_BA_states['Number']==i,'NAME'].values[0]
    state = df_BA_states.loc[df_BA_states['Number']==i,'State'].values[0]
    
    if str(area) == 'nan' or str(state) == 'nan':
        pass
    else:
    
        t = tuple([str(area),str(state)])
        
        if t in gen_keys:
            idx=gen_keys.index(t)
            gens[idx] += caps[x]
            
        else:
            gen_keys.append(t)
            gens.append(caps[x])
        
gen_weights = np.array(gens, dtype=float) / np.sum(gens) if np.sum(gens) > 0 else np.array([])

##############################
#Nodal reduction
##############################

# New rule: pick a fixed split of nodes
#   - 350 nodes from PJM
#   - 150 nodes from all other BAs in the EIC
# We first split candidates into PJM vs non-PJM, then apply the SAME
# selection logic (Step A/B/C) separately in each group.

PJM_BA_NAME = 'PJM'
PJM_TARGET_NODES = 350
OTHER_TARGET_NODES = 150

# Step C weights (Generation / extra Demand / Transmission)
# Old default: 50% / 0% / 50%
# New default: 1/3 / 1/3 / 1/3
DEFAULT_TYPE_WEIGHTS = (1/3, 1/3, 1/3)


def _safe_latlon(bus_num: int):
    """Return (lat, lon) tuple for a bus, or None if missing."""
    row = filter_nodes.loc[filter_nodes['Number'] == bus_num]
    if row.empty:
        return None
    lat = row['Substation Latitude'].values[0]
    lon = row['Substation Longitude'].values[0]
    if pd.isna(lat) or pd.isna(lon):
        return None
    return (float(lat), float(lon))


def _far_enough(candidate_bus: int, selected_buses: list, threshold_km: float) -> bool:
    """True if candidate is at least threshold_km away from ALL selected buses."""
    if threshold_km <= 0:
        return True

    T1 = _safe_latlon(candidate_bus)
    if T1 is None:
        # If we cannot locate the candidate, treat as not selectable under spacing rule
        return False

    for b in selected_buses:
        T2 = _safe_latlon(int(b))
        if T2 is None:
            continue
        dist_km = distance.distance(T1, T2).km
        if dist_km < threshold_km:
            return False
    return True


def _allocate_counts(remaining_nodes: int, weights=(1/3, 1/3, 1/3)):
    """
    Split remaining_nodes into (g_N, l_N, t_N) using weights, ensuring integer totals sum exactly.
    """
    w = np.array(weights, dtype=float)
    if np.any(w < 0) or not np.isfinite(w).all() or w.sum() <= 0:
        raise ValueError(f"Invalid weights: {weights}")

    w = w / w.sum()
    exact = remaining_nodes * w
    base = np.floor(exact).astype(int)
    leftover = int(remaining_nodes - base.sum())

    # Distribute leftover nodes to categories with largest fractional parts
    frac = exact - base
    order = np.argsort(-frac)  # descending
    for i in range(leftover):
        base[order[i % len(base)]] += 1

    g_N, l_N, t_N = map(int, base.tolist())
    return g_N, l_N, t_N


def _select_group_nodes(group_name: str, group_node_set: set, target_N: int,
                        type_weights=(1/3, 1/3, 1/3), spacing_km=5.0):
    """
    Apply the original selection logic within a group (PJM or a single non-PJM BA):

      Step A — Mandatory baseline demand nodes (one per BA×State, where Load MW > 0)
      Step B — Remaining nodes budget
      Step C — Split remaining into Generation / extra Demand / Transmission

    Practical safeguards added:
      * Handles empty candidate pools (no KeyErrors / RangeErrors)
      * If a category cannot fill its quota (even after relaxing spacing), we backfill from remaining nodes
        in the same group, prioritizing higher-voltage nodes (Nom kV) and then higher Load MW.
    """
    target_N = int(target_N)
    if target_N <= 0 or len(group_node_set) == 0:
        return [], [], []

    group_node_set = set(int(x) for x in group_node_set)

    # Load/meta for nodes in this group
    df_meta = df_BA_states[['Number', 'NAME', 'State']].copy()
    df_meta['Number'] = df_meta['Number'].astype(int)

    df_load_g_all = df_load[df_load['Number'].isin(group_node_set)].copy()
    df_load_g_all['Number'] = df_load_g_all['Number'].astype(int)
    df_load_g_all = df_load_g_all.merge(df_meta, on='Number', how='left')

    # -----------------------------
    # Step A: baseline demand nodes
    # -----------------------------
    demand_nodes_selected = []
    df_load_g = df_load_g_all.copy()
    df_load_g = df_load_g[df_load_g['Load MW'] > 0].dropna(subset=['NAME', 'State'])
    if not df_load_g.empty:
        idx = df_load_g.groupby(['NAME', 'State'])['Load MW'].idxmax()
        demand_nodes_selected = df_load_g.loc[idx, 'Number'].astype(int).tolist()

    # If baseline exceeds target, trim baseline by load
    if len(demand_nodes_selected) > target_N:
        df_base = df_load_g_all[df_load_g_all['Number'].isin(demand_nodes_selected)].copy()
        df_base = df_base.sort_values(by='Load MW', ascending=False).reset_index(drop=True)
        demand_nodes_selected = df_base['Number'].head(target_N).astype(int).tolist()
        print(f"[WARN] {group_name}: baseline demand nodes exceed target_N. Trimming baseline to {target_N}.")
        return demand_nodes_selected, [], []

    remaining_nodes = int(target_N - len(demand_nodes_selected))
    if remaining_nodes <= 0:
        return demand_nodes_selected, [], []

    # Step B/C: allocate counts by type
    g_N, l_N, t_N = _allocate_counts(remaining_nodes, weights=type_weights)

    # Helper: pick nodes from a ranked list with spacing, then (optionally) relax spacing to 0 km.
    def _pick_from_ranked(df_ranked: pd.DataFrame, id_col: str, n_needed: int, already_selected: list, label: str):
        n_needed = int(n_needed)
        if n_needed <= 0:
            return [], 0

        if df_ranked is None or df_ranked.empty:
            print(f"[WARN] {group_name}: no candidates available for {label}. Remaining={n_needed}.")
            return [], n_needed

        picked = []
        selected_set = set(int(x) for x in already_selected)

        # Pass 1: spacing_km
        for v in df_ranked[id_col].tolist():
            p = int(v)
            if p in selected_set or p in picked:
                continue
            if _far_enough(p, already_selected + picked, spacing_km):
                picked.append(p)
                if len(picked) >= n_needed:
                    return picked, 0

        # Pass 2: relax spacing to 0 km if still short
        if spacing_km > 0 and len(picked) < n_needed:
            print(f"[WARN] {group_name}: insufficient {label} candidates under spacing={spacing_km} km; relaxing spacing to 0 km to fill budget.")
            for v in df_ranked[id_col].tolist():
                p = int(v)
                if p in selected_set or p in picked:
                    continue
                # spacing=0 => always far enough
                if _far_enough(p, already_selected + picked, 0.0):
                    picked.append(p)
                    if len(picked) >= n_needed:
                        return picked, 0

        remaining = int(n_needed - len(picked))
        if remaining > 0:
            print(f"[WARN] {group_name}: unable to allocate all {label} nodes. Remaining={remaining}.")
        return picked, remaining

    # -----------------------------
    # Step C1: extra demand nodes
    # -----------------------------
    selected_so_far = demand_nodes_selected.copy()

    df_dem_ranks = df_load_g_all[~df_load_g_all['Number'].isin(selected_so_far)].copy()
    # Keep consistency with original script: prioritize nodes with positive load first
    df_dem_ranks = df_dem_ranks.sort_values(by='Load MW', ascending=False).reset_index(drop=True)

    extra_dem, l_rem = _pick_from_ranked(df_dem_ranks, 'Number', l_N, selected_so_far, 'extra demand')
    demand_nodes_selected += extra_dem
    selected_so_far = demand_nodes_selected.copy()

    # -----------------------------
    # Step C2: generation nodes
    # -----------------------------
    cap_by_bus = {}
    for b, c in zip(reduced_gen_buses, caps):
        try:
            cap_by_bus[int(b)] = float(c)
        except Exception:
            continue

    reduced_gen_buses_group = [int(b) for b in reduced_gen_buses if int(b) in group_node_set]
    unallocated_gens = [i for i in reduced_gen_buses_group if i not in set(selected_so_far)]

    df_gen_ranks = pd.DataFrame({
        'Bus': unallocated_gens,
        'MW': [cap_by_bus.get(int(i), 0.0) for i in unallocated_gens]
    }).sort_values(by='MW', ascending=False).reset_index(drop=True)

    gen_nodes_selected = []
    picked_gen, g_rem = _pick_from_ranked(df_gen_ranks, 'Bus', g_N, selected_so_far + gen_nodes_selected, 'generation')
    gen_nodes_selected += picked_gen
    selected_so_far = demand_nodes_selected + gen_nodes_selected

    # -----------------------------
    # Step C3: transmission nodes
    # -----------------------------
    df_trans_ranks = df_load_g_all[~df_load_g_all['Number'].isin(selected_so_far)].copy()
    # Prefer higher-voltage nodes; then higher load as tie-breaker
    if 'Nom kV' in df_trans_ranks.columns:
        df_trans_ranks = df_trans_ranks.sort_values(by=['Nom kV', 'Load MW'], ascending=[False, False]).reset_index(drop=True)
    else:
        df_trans_ranks = df_trans_ranks.sort_values(by='Load MW', ascending=False).reset_index(drop=True)

    trans_nodes_selected = []
    picked_trans, t_rem = _pick_from_ranked(df_trans_ranks, 'Number', t_N, selected_so_far + trans_nodes_selected, 'transmission')
    trans_nodes_selected += picked_trans
    selected_so_far = demand_nodes_selected + gen_nodes_selected + trans_nodes_selected

    # -----------------------------
    # Backfill within this group if any category fell short
    # -----------------------------
    deficit = int(target_N - len(set(selected_so_far)))
    if deficit > 0:
        df_backfill = df_load_g_all[~df_load_g_all['Number'].isin(selected_so_far)].copy()
        if 'Nom kV' in df_backfill.columns:
            df_backfill = df_backfill.sort_values(by=['Nom kV', 'Load MW'], ascending=[False, False]).reset_index(drop=True)
        else:
            df_backfill = df_backfill.sort_values(by='Load MW', ascending=False).reset_index(drop=True)

        picked_backfill, rem = _pick_from_ranked(df_backfill, 'Number', deficit, selected_so_far, 'backfill')
        # Treat backfill as transmission nodes for bookkeeping
        trans_nodes_selected += picked_backfill

    return demand_nodes_selected, gen_nodes_selected, trans_nodes_selected


def _read_annual_ba_demand(load_csv_path: str) -> pd.Series:
    """
    Read BA hourly load table and return annual demand per BA (column-wise sum).
    Expected format (per BA_load_correction.py outputs):
      - first column: time index (0-8759 or timestamps)
      - header row: BA abbreviations
    """
    df_ba = pd.read_csv(load_csv_path, header=0)
    if df_ba.shape[1] < 2:
        raise ValueError(f"BA load file has too few columns: {load_csv_path}")

    time_col = df_ba.columns[0]
    df_vals = df_ba.drop(columns=[time_col])

    # Normalize column labels
    df_vals.columns = df_vals.columns.astype(str).str.upper().str.strip()

    # Numeric coercion
    for c in df_vals.columns:
        df_vals[c] = pd.to_numeric(df_vals[c], errors='coerce').fillna(0.0)

    annual = df_vals.sum(axis=0)  # column-wise sum
    annual = annual.astype(float)
    return annual


def _allocate_integer_targets_from_demand(demand_by_ba: dict, total_nodes: int) -> dict:
    """
    Convert BA annual-demand weights into integer node targets summing exactly to total_nodes.

    We use a largest-remainder method (Hamilton apportionment):
      1) compute quotas = total_nodes * demand / sum(demand)
      2) take floor(quota)
      3) distribute remaining nodes to BAs with largest fractional parts

    This keeps the total exactly == total_nodes (unlike naive ceil).
    """
    total_nodes = int(total_nodes)
    if total_nodes <= 0:
        return {k: 0 for k in demand_by_ba.keys()}

    # Clean
    cleaned = {str(k).upper(): float(v) if np.isfinite(v) else 0.0 for k, v in demand_by_ba.items()}
    cleaned = {k: max(0.0, v) for k, v in cleaned.items()}
    total_demand = float(sum(cleaned.values()))

    bas = list(cleaned.keys())
    if len(bas) == 0:
        return {}

    if total_demand <= 0:
        # Fallback: uniform apportionment across BAs with any candidate nodes
        q, r = divmod(total_nodes, len(bas))
        out = {k: int(q) for k in bas}
        for k in bas[:r]:
            out[k] += 1
        return out

    quotas = {k: (total_nodes * cleaned[k] / total_demand) for k in bas}
    floors = {k: int(np.floor(quotas[k])) for k in bas}
    remainder = int(total_nodes - sum(floors.values()))

    frac = sorted(((k, quotas[k] - floors[k]) for k in bas), key=lambda x: x[1], reverse=True)
    out = floors.copy()
    for i in range(remainder):
        out[frac[i % len(frac)][0]] += 1

    # Sanity: exact sum
    assert sum(out.values()) == total_nodes, "Internal allocation error: targets do not sum to total_nodes."
    return out




# -----------------------------
# Apply PJM + non-PJM split
# -----------------------------
nodes_pjm = set(
    df_BA_states.loc[df_BA_states['BA_ABBR'] == PJM_BA_NAME, 'Number']
    .dropna().astype(int).tolist()
)

# Non-PJM nodes grouped by BA abbreviation (used for per-BA allocation/selection)
df_non_pjm = df_BA_states[
    df_BA_states['BA_ABBR'].notna() & (df_BA_states['BA_ABBR'] != PJM_BA_NAME)
].copy()
df_non_pjm['BA_ABBR'] = df_non_pjm['BA_ABBR'].astype(str).str.upper()

other_bas = sorted(df_non_pjm['BA_ABBR'].unique().tolist())
nodes_other_by_ba = {
    ba: set(df_non_pjm.loc[df_non_pjm['BA_ABBR'] == ba, 'Number'].dropna().astype(int).tolist())
    for ba in other_bas
}
nodes_other = set().union(*nodes_other_by_ba.values()) if len(nodes_other_by_ba) > 0 else set()

# -----------------------------
# Determine non-PJM BA targets using 2019 annual demand shares (excluding PJM)
# -----------------------------
load_csv = os.path.join(base_dir, 'Load', 'BA_load_corrected_2019.csv')

try:
    annual_ba_demand = _read_annual_ba_demand(load_csv)
except Exception as e:
    print(f"[WARN] Unable to read BA load file for allocation: {load_csv}. Falling back to uniform non-PJM allocation. Error: {e}")
    annual_ba_demand = pd.Series(dtype=float)

demand_by_ba = {ba: float(annual_ba_demand.get(ba, 0.0)) for ba in other_bas}
non_pjm_targets = _allocate_integer_targets_from_demand(demand_by_ba, OTHER_TARGET_NODES)

# Save demand factors / targets table for transparency
try:
    total_non_pjm = float(sum(max(0.0, v) for v in demand_by_ba.values()))
    df_alloc = pd.DataFrame({
        'BA_ABBR': other_bas,
        'Annual_Demand_2019': [float(demand_by_ba.get(ba, 0.0)) for ba in other_bas],
    })
    df_alloc['Factor'] = df_alloc['Annual_Demand_2019'] / total_non_pjm if total_non_pjm > 0 else 1.0 / max(len(other_bas), 1)
    df_alloc['Target_Nodes'] = df_alloc['BA_ABBR'].map(lambda x: int(non_pjm_targets.get(x, 0)))
    df_alloc = df_alloc.sort_values('Target_Nodes', ascending=False).reset_index(drop=True)
    os.makedirs(os.path.join(base_dir, 'reduced_network'), exist_ok=True)
    df_alloc.to_csv(os.path.join(base_dir, 'reduced_network', 'non_pjm_ba_node_targets_2019.csv'), index=False)
except Exception as _:
    pass

print(f"Non-PJM per-BA targets computed. Total targets={sum(non_pjm_targets.values())} (expected {OTHER_TARGET_NODES}).")


for NN in RTS:

    if NN != (PJM_TARGET_NODES + OTHER_TARGET_NODES):
        print(f"[WARN] RTS includes NN={NN}, but split targets are fixed at {PJM_TARGET_NODES}+{OTHER_TARGET_NODES}=500. Proceeding with fixed split and ignoring NN for allocation.")
    NN_total = PJM_TARGET_NODES + OTHER_TARGET_NODES

    d_pjm, g_pjm, t_pjm = _select_group_nodes(
        group_name='PJM',
        group_node_set=nodes_pjm,
        target_N=PJM_TARGET_NODES,
        type_weights=DEFAULT_TYPE_WEIGHTS,
        spacing_km=distance_threshold
    )

    # -----------------------------
    # non-PJM: apply Step A/B/C within EACH non-PJM BA using the load-based targets
    # -----------------------------
    d_oth_all, g_oth_all, t_oth_all = [], [], []

    # 1) BA-by-BA selection
    for ba in other_bas:
        target_ba = int(non_pjm_targets.get(ba, 0))
        if target_ba <= 0:
            continue

        d_ba, g_ba, t_ba = _select_group_nodes(
            group_name=f'non-PJM:{ba}',
            group_node_set=nodes_other_by_ba.get(ba, set()),
            target_N=target_ba,
            type_weights=DEFAULT_TYPE_WEIGHTS,
            spacing_km=distance_threshold
        )
        d_oth_all += d_ba
        g_oth_all += g_ba
        t_oth_all += t_ba

    # 2) If any BA cannot supply enough candidates to meet its target, backfill from remaining non-PJM nodes
    selected_other = set(d_oth_all + g_oth_all + t_oth_all)
    deficit = int(OTHER_TARGET_NODES - len(selected_other))
    if deficit > 0:
        remaining_pool = set(nodes_other) - set(selected_other)
        if len(remaining_pool) > 0:
            d_fill, g_fill, t_fill = _select_group_nodes(
                group_name='non-PJM:BACKFILL',
                group_node_set=remaining_pool,
                target_N=deficit,
                type_weights=DEFAULT_TYPE_WEIGHTS,
                spacing_km=distance_threshold
            )
            d_oth_all += d_fill
            g_oth_all += g_fill
            t_oth_all += t_fill

    demand_nodes_selected = d_pjm + d_oth_all

    gen_nodes_selected = g_pjm + g_oth_all
    trans_nodes_selected = t_pjm + t_oth_all

    selected_nodes = demand_nodes_selected + gen_nodes_selected + trans_nodes_selected

    # Sanity checks
    n_unique = len(set(selected_nodes))
    if n_unique != len(selected_nodes):
        print("[WARN] Duplicate nodes detected across categories; de-duplicating while preserving order.")
        seen = set()
        selected_nodes = [x for x in selected_nodes if (x not in seen and not seen.add(x))]
        # refresh category lists (best-effort)
        demand_nodes_selected = [x for x in demand_nodes_selected if x in selected_nodes]
        gen_nodes_selected = [x for x in gen_nodes_selected if x in selected_nodes]
        trans_nodes_selected = [x for x in trans_nodes_selected if x in selected_nodes]

    print(f"Selected nodes total: {len(selected_nodes)} (PJM={len(d_pjm)+len(g_pjm)+len(t_pjm)}, non-PJM={len(d_oth_all)+len(g_oth_all)+len(t_oth_all)})")

    # -----------------------------
    # Plot
    # -----------------------------
    fig, ax = plt.subplots()
    states_gdf.plot(ax=ax, color='white', edgecolor='black', linewidth=0.5)
    nodes_df.plot(ax=ax, color='lightgray', alpha=1)
    M = 18

    G_NODES = nodes_df[nodes_df['Number'].isin(gen_nodes_selected)]
    G_NODES.plot(ax=ax, color='deepskyblue', markersize=M, alpha=1, edgecolor='black', linewidth=0.3)

    D_NODES = nodes_df[nodes_df['Number'].isin(demand_nodes_selected)]
    D_NODES.plot(ax=ax, color='deeppink', markersize=M, alpha=1, edgecolor='black', linewidth=0.3)

    T_NODES = nodes_df[nodes_df['Number'].isin(trans_nodes_selected)]
    T_NODES.plot(ax=ax, color='limegreen', markersize=M, alpha=1, edgecolor='black', linewidth=0.3)

    ax.set_box_aspect(1)
    ax.set_xlim(-1000000, 2750000)
    ax.set_ylim([-2000000, 850000])
    plt.axis('off')
    fname = 'reduced_network/draft_topology_PJM350_other150.jpg'
    plt.savefig(os.path.join(base_dir, fname), dpi=330)

    # -----------------------------
    # Save selected/excluded nodes
    # -----------------------------
    df_all_buses = pd.read_csv(os.path.join(base_dir, 'Interconnections/Buses_EIA.csv'), header=0)
    full = list(df_all_buses['Number'])

    excluded = [i for i in full if int(i) not in set(selected_nodes)]

    df_excluded_nodes = pd.DataFrame(excluded, columns=['ExcludedNodes'])
    f = 'reduced_network/excluded_nodes_PJM350_other150.csv'
    df_excluded_nodes.to_csv(os.path.join(base_dir, f), index=None)

    df_selected_nodes = pd.DataFrame(selected_nodes, columns=['SelectedNodes'])
    f = 'reduced_network/selected_nodes_PJM350_other150.csv'
    df_selected_nodes.to_csv(os.path.join(base_dir, f), index=None)

    # -----------------------------
    # Save counts of retained nodes by BA (original shapefile NAME)
    # -----------------------------
    try:
        os.makedirs(os.path.join(base_dir, 'reduced_network'), exist_ok=True)
    except Exception:
        pass

    # Map selected nodes -> BA NAME/State using df_BA_states (keeps original NAME)
    df_sel = pd.DataFrame({'Number': [int(x) for x in selected_nodes]})
    df_sel['Category'] = np.where(df_sel['Number'].isin(demand_nodes_selected), 'Demand',
                                 np.where(df_sel['Number'].isin(gen_nodes_selected), 'Generation', 'Transmission'))
    df_sel = df_sel.merge(df_BA_states[['Number', 'NAME', 'State', 'BA_ABBR']], on='Number', how='left')

    # Total counts per BA (by original NAME)
    df_counts = (df_sel.groupby(['NAME'], dropna=False)['Number']
                     .nunique()
                     .reset_index(name='N_Selected'))

    # Optional breakdown by category
    df_cat = (df_sel.pivot_table(index='NAME', columns='Category', values='Number',
                                 aggfunc=lambda x: x.nunique(), fill_value=0)
                  .reset_index())

    df_counts = df_counts.merge(df_cat, on='NAME', how='left')

    # Add abbreviation for convenience (does not affect other scripts)
    df_abbr = (df_sel.groupby('NAME')['BA_ABBR'].agg(lambda x: next((v for v in x if pd.notna(v)), np.nan)).reset_index())
    df_counts = df_counts.merge(df_abbr, on='NAME', how='left')

    f = 'reduced_network/retained_nodes_by_BA_PJM350_other150.csv'
    df_counts.sort_values('N_Selected', ascending=False).to_csv(os.path.join(base_dir, f), index=False)