# -*- coding: utf-8 -*-
"""
EICDataSetup_MW.py adjusted for the raw-generator outage-capacity workflow.

This version keeps the PJM script's existing data flow for load, wind, solar,
hydro, fuel prices, and outputs, but changes the outage inputs:

- It no longer reads df_dict2_{NN}.npy.
- It no longer writes GADS category outage sets.
- It reads the outage-adjusted, reduced-network hourly limits created by
  reduced_network_data_allocation*_updated.py:
      HorizonGenLimits_base_{NN}_y_{year}.csv
      HorizonMustrunLimits_base_{NN}_y_{year}.csv
- It writes those values directly into EIC_data.dat as:
      SimGenLimit
      SimMustrunLimit

This MW-specific version keeps the +MW transmission-expansion filename style:
      Exp500_simple_MW_-50_2019
"""

import csv
import pandas as pd
import numpy as np
import os
import re
from pathlib import Path

######=================================================########
######               Segment A.1                       ########
######=================================================########

SimDays = 365
SimHours = SimDays * 24
HorizonHours = 24  ## planning horizon

data_name = 'EIC_data'
base_dir = 'Data'
data_allocation_dir = os.path.join(base_dir, 'data_allocation')


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ampl_name(x) -> str:
    """Return a safe AMPL/Pyomo symbol name used consistently in data.dat."""
    s = str(x)
    s = s.replace(' ', '_')
    s = s.replace('&', '_')
    s = s.replace('.', '')
    s = s.replace('-', '_')
    return s


def _format_case_value(value: str) -> str:
    """Keep integer-like folder values stable, e.g., 300.0 -> 300."""
    text = str(value)
    try:
        f = float(text)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return text


def _must_read_csv(path, **kwargs):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path, **kwargs)


def _read_required_hourly_wide(path: str, expected_rows: int = SimHours) -> pd.DataFrame:
    """
    Read a required 8760-row wide hourly table.

    Supported formats:
        Hour, col_1, col_2, ...
        Time, col_1, col_2, ...
        unnamed/index column, col_1, col_2, ...
        col_1, col_2, ...       # row position is treated as Hour 1..N

    Returned dataframe is indexed by 1-based Hour and contains numeric values.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required hourly limit file not found: {path}")

    df = pd.read_csv(path, header=0)
    if len(df) != expected_rows:
        raise ValueError(f"{os.path.basename(path)} has {len(df)} rows; expected {expected_rows}.")

    first_col = str(df.columns[0])
    first_lower = first_col.lower()

    if first_lower.startswith('unnamed') or first_lower in {'hour', 'time', 'hour_of_year'}:
        hour_values = pd.to_numeric(df.iloc[:, 0], errors='coerce')
        df = df.drop(columns=[df.columns[0]])

        if hour_values.notna().all():
            hour_values = hour_values.astype(int)
            if hour_values.min() == 0 and hour_values.max() == expected_rows - 1:
                df.index = hour_values + 1
            else:
                df.index = hour_values
        else:
            df.index = range(1, len(df) + 1)
    else:
        df.index = range(1, len(df) + 1)

    df.index.name = 'Hour'
    df = df.apply(pd.to_numeric, errors='coerce').fillna(0.0)
    return df


def _build_column_lookup(df: pd.DataFrame) -> dict:
    """Map original column names and AMPL-safe column names to dataframe columns."""
    lookup = {}
    for col in df.columns:
        lookup[str(col)] = col
        lookup[_ampl_name(col)] = col
    return lookup


def _hourly_value_from_wide(
    df: pd.DataFrame,
    column_lookup: dict,
    entity_name: str,
    hour_1based: int,
    default: float = 0.0,
) -> float:
    """Safely read one value from a 1-based hourly wide table."""
    col = column_lookup.get(str(entity_name)) or column_lookup.get(_ampl_name(entity_name))
    if col is None:
        return default

    try:
        value = df.loc[hour_1based, col]
    except Exception:
        return default

    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


# ------------------------------------------------------------------
# Helper: build and write EIC_data.dat for a single Exp folder
# ------------------------------------------------------------------

def build_eic_dat_for_exp(exp_path: Path, NN: str, trans_tag: str, year: str):
    """Read all inputs for (NN, transmission case, year) from Data/data_allocation
    and write EIC_data.dat into the given Exp folder path.
    """
    # ---- Read parameters for dispatchable resources ----
    df_gen = _must_read_csv(os.path.join(data_allocation_dir, f'data_genparams_{NN}.csv'), header=0)

    # Include oil because the updated raw-generator outage aggregation creates
    # node-level oil limits, e.g., bus_123_oil, in HorizonGenLimits_base_*.
    thermal_generators_df = df_gen.loc[
        df_gen['typ'].isin(['coal', 'ngcc', 'ngct', 'oil'])
    ].copy()
    thermal_generators_names = [*thermal_generators_df['name']]

    # ---- Generation and transmission data ----
    df_bustounitmap = _must_read_csv(os.path.join(data_allocation_dir, f'gen_mat_{NN}.csv'), header=0)
    df_linetobusmap = _must_read_csv(os.path.join(data_allocation_dir, f'line_to_bus_{NN}_{trans_tag}.csv'), header=0)
    df_line_params = _must_read_csv(os.path.join(data_allocation_dir, f'line_params_{NN}_{trans_tag}.csv'), header=0)
    lines = list(df_line_params['line'])

    # ---- Hourly nodal timeseries ----
    df_solar = _must_read_csv(os.path.join(data_allocation_dir, f'nodal_solar_{NN}_y_{year}.csv'), header=0)
    df_wind  = _must_read_csv(os.path.join(data_allocation_dir, f'nodal_wind_{NN}_y_{year}.csv'),  header=0)
    df_hydro = _must_read_csv(os.path.join(data_allocation_dir, f'nodal_hydro_{NN}.csv'),          header=0)
    df_load  = _must_read_csv(os.path.join(data_allocation_dir, f'nodal_load_{NN}_y_{year}.csv'),  header=0)

    # ---- Fuel prices ----
    df_fuel = _must_read_csv(os.path.join(data_allocation_dir, f'Fuel_prices_{NN}_y_{year}.csv'), header=0)

    # ---- Outage-adjusted hourly limits from raw-generator allocation ----
    gen_limit_path = os.path.join(data_allocation_dir, f'HorizonGenLimits_base_{NN}_y_{year}.csv')
    mustrun_limit_path = os.path.join(data_allocation_dir, f'HorizonMustrunLimits_base_{NN}_y_{year}.csv')

    df_gen_limits = _read_required_hourly_wide(gen_limit_path, expected_rows=SimHours)
    df_mustrun_limits = _read_required_hourly_wide(mustrun_limit_path, expected_rows=SimHours)

    gen_limit_lookup = _build_column_lookup(df_gen_limits)
    mustrun_limit_lookup = _build_column_lookup(df_mustrun_limits)

    print(f'Using hourly thermal outage limits from: {os.path.basename(gen_limit_path)}')
    print(f'Using hourly must-run limits from: {os.path.basename(mustrun_limit_path)}')

    # ---- Cleanup: drop empty time series columns ----
    for _df in (df_solar, df_wind, df_hydro):
        empty = []
        for col in _df.columns:
            if pd.to_numeric(_df[col], errors='coerce').fillna(0).sum() <= 0:
                empty.append(col)
        if empty:
            _df.drop(columns=empty, inplace=True)

    ######=================================================########
    ######               Segment A.3                       ########
    ######=================================================########

    all_nodes = list(df_load.columns)
    all_thermals = list(df_fuel.columns)

    # ---- Sanity checks for outage limit coverage ----
    missing_gen_limit_cols = [
        z for z in thermal_generators_names
        if str(z) not in gen_limit_lookup and _ampl_name(z) not in gen_limit_lookup
    ]
    if missing_gen_limit_cols:
        raise ValueError(
            f"{os.path.basename(gen_limit_path)} is missing {len(missing_gen_limit_cols)} "
            f"thermal generator columns required by the model. "
            f"Examples: {missing_gen_limit_cols[:10]}"
        )

    missing_mustrun_cols = [
        z for z in all_nodes
        if str(z) not in mustrun_limit_lookup and _ampl_name(z) not in mustrun_limit_lookup
    ]
    if missing_mustrun_cols:
        raise ValueError(
            f"{os.path.basename(mustrun_limit_path)} is missing {len(missing_mustrun_cols)} "
            f"bus columns required by the model. Examples: {missing_mustrun_cols[:10]}"
        )

    ######=================================================########
    ######               Write data.dat                     ########
    ######=================================================########

    out_path = Path(exp_path) / f'{data_name}.dat'
    with open(out_path, 'w') as f:
        # -------- generator sets by type --------
        # Coal
        f.write('set Coal :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'coal':
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # Oil
        f.write('set Oil :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'oil':
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # Gas
        f.write('set Gas :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] in ('ngcc', 'ngct'):
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # Hydro
        f.write('set Hydro :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'hydro':
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # Solar
        f.write('set Solar :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'solar':
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # Wind
        f.write('set Wind :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'wind':
                f.write(_ampl_name(df_gen.loc[i, 'name']) + ' ')
        f.write(';\n\n')

        # -------- Unit outage category sets intentionally removed --------
        # The raw-generator workflow already produces model-ready hourly limits.
        # They are written below as SimGenLimit and SimMustrunLimit, so the
        # wrapper should not subtract category-level lost capacity again.

        # -------- Sets: buses & lines --------
        f.write('set buses :=\n')
        for z in all_nodes:
            f.write(str(z) + ' ')
        f.write(';\n\n')

        f.write('set lines :=\n')
        for z in lines:
            f.write(_ampl_name(z) + ' ')
        f.write(';\n\n')

        # -------- Simulation period --------
        f.write('param SimHours := %d;' % SimHours); f.write('\n')
        f.write('param SimDays:= %d;' % SimDays); f.write('\n\n')
        f.write('param HorizonHours := %d;' % HorizonHours); f.write('\n\n')

        # -------- Generator parameter matrix --------
        f.write('param:\t')
        for c in df_gen.columns:
            if c != 'name':
                f.write(c + '\t')
        f.write(':=\n\n')
        for i in range(len(df_gen)):
            for c in df_gen.columns:
                if c == 'name':
                    f.write(_ampl_name(df_gen.loc[i, 'name']) + '\t')
                else:
                    f.write(str(df_gen.loc[i, c]) + '\t')
            f.write('\n')
        f.write(';\n\n')

        # Hourly generator capacity after outages.
        f.write('param:\tSimGenLimit:=\n')
        for z in thermal_generators_names:
            thermal_gen_capacity = float(
                thermal_generators_df.loc[thermal_generators_df['name'] == z]['maxcap'].values[0]
            )
            for h in range(SimHours):
                hour = h + 1
                value = _hourly_value_from_wide(
                    df_gen_limits,
                    gen_limit_lookup,
                    str(z),
                    hour,
                    default=thermal_gen_capacity,
                )
                # Safety bound: the reduced limit should not exceed model maxcap.
                value = max(0.0, min(float(value), thermal_gen_capacity))
                f.write(_ampl_name(z) + '\t' + str(hour) + '\t' + str(value) + '\n')
        f.write(';\n\n')

        # Hourly must-run capacity after nuclear outages.
        f.write('param:\tSimMustrunLimit:=\n')
        for z in all_nodes:
            for h in range(SimHours):
                hour = h + 1
                value = _hourly_value_from_wide(
                    df_mustrun_limits,
                    mustrun_limit_lookup,
                    str(z),
                    hour,
                    default=0.0,
                )
                value = max(0.0, float(value))
                f.write(str(z) + '\t' + str(hour) + '\t' + str(value) + '\n')
        f.write(';\n\n')

        # Transmission paths (limits & reactance)
        f.write('param:\tFlowLim\tReactance :=\n')
        for idx, z in enumerate(lines):
            f.write(
                _ampl_name(z) + '\t' +
                str(df_line_params.loc[idx, 'limit']) + '\t' +
                str(df_line_params.loc[idx, 'reactance']) + '\n'
            )
        f.write(';\n\n')

        # Hourly time series
        # Load
        f.write('param:\tSimDemand:=\n')
        for z in all_nodes:
            for h in range(len(df_load)):
                f.write(str(z) + '\t' + str(h+1) + '\t' + str(df_load.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Solar
        f.write('param:\tSimSolar:=\n')
        for z in df_solar.columns:
            for h in range(len(df_solar)):
                f.write(str(z) + '_SOLAR' + '\t' + str(h+1) + '\t' + str(df_solar.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Wind
        f.write('param:\tSimWind:=\n')
        for z in df_wind.columns:
            for h in range(len(df_wind)):
                f.write(str(z) + '_WIND' + '\t' + str(h+1) + '\t' + str(df_wind.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Hydro: keep the existing PJM script's SimHydro format unchanged.
        f.write('param:\tSimHydro:=\n')
        for z in df_hydro.columns:
            for h in range(len(df_hydro)):
                f.write(str(z) + '_HYDRO' + '\t' + str(h+1) + '\t' + str(df_hydro.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Maps
        f.write('param BustoUnitMap:\n\t')
        for j in df_bustounitmap.columns:
            if j != 'name':
                f.write(str(j) + '\t')
        f.write(':=\n')
        for i in range(len(df_bustounitmap)):
            for j in df_bustounitmap.columns:
                value = df_bustounitmap.loc[i, j]
                if j == 'name':
                    value = _ampl_name(value)
                f.write(str(value) + '\t')
            f.write('\n')
        f.write(';\n\n')

        f.write('param LinetoBusMap:\n\t')
        for j in df_linetobusmap.columns:
            if j != 'line':
                f.write(str(j) + '\t')
        f.write(':=\n')
        for i in range(len(df_linetobusmap)):
            for j in df_linetobusmap.columns:
                value = df_linetobusmap.loc[i, j]
                if j == 'line':
                    value = _ampl_name(value)
                f.write(str(value) + '\t')
            f.write('\n')
        f.write(';\n\n')

        # Daily fuel prices
        f.write('param:\tSimFuelPrice:=\n')
        for z in all_thermals:
            for d in range(int(SimHours/24)):
                f.write(_ampl_name(z) + '\t' + str(d+1) + '\t' + str(df_fuel.loc[d, z]) + '\n')
        f.write(';\n\n')

    print('Complete:', out_path)


# ------------------------------------------------------------------
# Main: iterate over all Exp* folders in CWD and generate EIC_data.dat
# ------------------------------------------------------------------

def _parse_exp_folder_name(name: str):
    """
    Parse MW folders created by the updated +MW allocation script.

    Supported examples:
        Exp500_simple_MW_25_2019
        Exp500_simple_MW_-50_2019
    """
    if not name.startswith('Exp'):
        return None

    rest = name[3:]
    m = re.match(r'^(?P<NN>\d+)(?P<tail>_.*)$', rest)
    if m is None:
        return None

    NN = m.group('NN')
    parts = m.group('tail').strip('_').split('_')

    if len(parts) < 4:
        return None

    year = parts[-1]
    if not re.fullmatch(r'\d{4}', year):
        return None

    # MW-specific Datasetup: only process folders with the literal MW token.
    if parts[-3].upper() != 'MW':
        return None

    trans_value = _format_case_value(parts[-2])
    trans_tag = f'MW_{trans_value}'

    return NN, trans_tag, year


def main():
    cwd = Path.cwd()
    exp_dirs = [p for p in cwd.iterdir() if p.is_dir() and p.name.startswith('Exp')]
    matched = []
    for p in exp_dirs:
        parsed = _parse_exp_folder_name(p.name)
        if parsed:
            matched.append((p, *parsed))

    if not matched:
        raise RuntimeError(
            "No matching Exp folders found. Expected names like "
            "'Exp500_simple_MW_25_2019' or 'Exp500_simple_MW_-50_2019'."
        )

    for exp_path, NN, trans_tag, year in matched:
        print(f"EICDataSetup case: NN={NN}, tag={trans_tag}, year={year}, folder={exp_path.name}")
        build_eic_dat_for_exp(exp_path, NN, trans_tag, year)


if __name__ == '__main__':
    main()
